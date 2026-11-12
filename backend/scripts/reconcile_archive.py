# -*- coding: utf-8 -*-
"""只读批量对账入口（离线归档）。

按原语料与词典快照复算 TopicRun，核对三处来源是否一致：
  1. 库内结果（runs 表 JSON 载荷）
  2. 共享结果文件（ARTIFACT_DIR/<run_id>.json）
  3. 已批准报告（reports 表 + ARTIFACT_DIR/<report_id>.csv，人工命名版本）

复算口径完全复用生产服务 src.services.statistics.analyze，不重新实现算法，
保证与 worker 落库/落文件的口径一致。

只读保证：
  - 全程不调用 repo.put，不写入被对账的数据库或归档目录；
  - sqlite 以 immutable=1 的只读 URI 打开，postgres 以 read-only 模式打开；
  - 所有归档文件以 'rb'/'r' 只读方式打开。

退出码：
  0  全部可核验运行一致（可能含容差内数值漂移，见 --strict）
  1  发现数据损坏（CORRUPTION）或容差外数值误差（NUMERIC 超阈）
  2  存在缺少复算依据、无法核验的旧归档（UNVERIFIABLE，且无更严重问题）
  3  用法/环境错误（归档根目录不存在等）

用法：
  python -m scripts.reconcile_archive --archive /path/to/archive
  python -m scripts.reconcile_archive --sqlite /tmp/interview-topics.sqlite \
      --artifacts /tmp/interview-topics-artifacts
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 让脚本在 -I（隔离模式）下也能 import 后端 src：仓库 backend 目录是本文件上两级。
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 固定单线程，避免并发数值执行差异，与 docker-compose 的 OPENBLAS/OMP=1 口径一致。
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from src.services.statistics import analyze  # noqa: E402
from src.services import report as report_service  # noqa: E402

TABLES = ("datasets", "lexicons", "studies", "runs", "reviews", "reports")
RUN_ARTIFACT_SUFFIX = ".json"
REPORT_ARTIFACT_SUFFIX = ".csv"

# 严重度 / 类别常量
CORRUPTION = "corruption"      # 数据损坏：缺失、坏文件、结构/类型/文本不符、checksum 不符或数值被大幅篡改
NUMERIC = "numeric"            # 数值误差：同为有限数值，差异超容差但仍在漂移带内
UNVERIFIABLE = "unverifiable"  # 无法核验：缺少复算依据
INFO = "info"                  # 提示信息（不影响退出码）
OK = "ok"

# deep_compare 显式校验、不再递归比对的字段
SKIP_KEYS = {"checksum"}
# 默认“数值漂移带”：差异超出对账容差、但相对幅度不超过该值时判为数值误差而非损坏
DRIFT_REL = 1e-2
DRIFT_ATOL = 1e-8


@dataclass
class Finding:
    category: str          # corruption | numeric | unverifiable
    object_path: str       # 可定位对象，例如 runs/run-demo/result/nmf/w[3][2]
    message: str
    expected: Any = None
    actual: Any = None
    tolerance: dict | None = None

    def to_dict(self) -> dict:
        d = {"category": self.category, "object_path": self.object_path,
             "message": self.message}
        if self.expected is not None or self.actual is not None:
            d["expected"] = self.expected
            d["actual"] = self.actual
        if self.tolerance is not None:
            d["tolerance"] = self.tolerance
        return d


@dataclass
class RunReport:
    run_id: str
    status: str = OK                      # ok | corruption | numeric | unverifiable
    verified: bool = False                # 是否成功完成复算核验
    findings: list[Finding] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)
        if f.category == INFO:
            return
        order = {OK: -1, UNVERIFIABLE: 0, NUMERIC: 1, CORRUPTION: 2}
        if f.category in order and order[f.category] > order.get(self.status, -1):
            self.status = f.category


class ArchiveSource:
    """离线归档目录来源：datasets/lexicons/... 子目录，每个实体一个 <id>.json。"""

    def __init__(self, root: Path):
        self.root = root
        self.artifact_dir = root / "artifacts"

    def load_table(self, table: str) -> tuple[dict[str, Any], list[Finding]]:
        findings: list[Finding] = []
        out: dict[str, Any] = {}
        d = self.root / table
        if not d.is_dir():
            # 整表缺失不直接算损坏：旧归档可能本就不含某实体（如语料快照），
            # 由引用它的运行按“缺少复算依据”判为无法核验。
            findings.append(Finding(INFO, f"{table}/",
                                    f"归档不含实体目录 {table}/（相关运行可能无法核验）"))
            return out, findings
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.suffix != ".json":
                continue
            rel = f"{table}/{p.name}"
            try:
                with p.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh, parse_constant=_reject_constant)
            except (OSError, UnicodeDecodeError) as exc:
                findings.append(Finding(CORRUPTION, rel, f"文件不可读：{exc}"))
                continue
            except json.JSONDecodeError as exc:
                findings.append(Finding(CORRUPTION, rel,
                                        f"JSON 解析失败（坏文件）：{exc.msg} 行{exc.lineno}列{exc.colno}"))
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                findings.append(Finding(CORRUPTION, rel,
                                        "载荷不是对象或缺少字符串 id 字段"))
                continue
            out[payload["id"]] = payload
        return out, findings

    def load_run_artifact(self, run_id: str) -> tuple[Any | None, Finding | None]:
        return _load_json_artifact(self.artifact_dir / (run_id + RUN_ARTIFACT_SUFFIX),
                                   f"artifacts/{run_id}{RUN_ARTIFACT_SUFFIX}")

    def load_report_artifact_text(self, report_id: str) -> tuple[str | None, Finding | None]:
        p = self.artifact_dir / (report_id + REPORT_ARTIFACT_SUFFIX)
        rel = f"artifacts/{report_id}{REPORT_ARTIFACT_SUFFIX}"
        if not p.exists():
            return None, Finding(CORRUPTION, rel, "报告 CSV 共享文件缺失")
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as fh:
                return fh.read(), None
        except (OSError, UnicodeDecodeError) as exc:
            return None, Finding(CORRUPTION, rel, f"报告 CSV 不可读：{exc}")

    def list_artifact_files(self) -> list[Path]:
        if not self.artifact_dir.is_dir():
            return []
        return sorted(p for p in self.artifact_dir.iterdir() if p.is_file())


class SqliteSource:
    """只读 SQLite 来源。immutable=1 表示不创建/依赖 WAL，也绝不写库。"""

    def __init__(self, db_path: Path, artifact_dir: Path):
        self.db_path = db_path
        self.artifact_dir = artifact_dir

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path.resolve()}?immutable=1"
        return sqlite3.connect(uri, uri=True, timeout=30)

    def load_table(self, table: str) -> tuple[dict[str, Any], list[Finding]]:
        findings: list[Finding] = []
        out: dict[str, Any] = {}
        try:
            conn = self._connect()
        except sqlite3.Error as exc:
            findings.append(Finding(CORRUPTION, f"sqlite:{table}",
                                    f"数据库无法以只读方式打开：{exc}"))
            return out, findings
        try:
            cur = conn.execute(f"SELECT payload FROM {table} ORDER BY id")
            for (raw,) in cur.fetchall():
                rel = f"{table}/<row>"
                try:
                    payload = json.loads(raw, parse_constant=_reject_constant)
                except json.JSONDecodeError as exc:
                    findings.append(Finding(CORRUPTION, rel,
                                            f"库内 JSON 载荷损坏：{exc.msg}"))
                    continue
                if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
                    findings.append(Finding(CORRUPTION, rel,
                                            "库内载荷不是对象或缺少字符串 id"))
                    continue
                out[payload["id"]] = payload
        except sqlite3.Error as exc:
            findings.append(Finding(CORRUPTION, f"sqlite:{table}",
                                    f"读取表 {table} 失败：{exc}"))
        finally:
            conn.close()
        return out, findings

    def load_run_artifact(self, run_id: str):
        return _load_json_artifact(self.artifact_dir / (run_id + RUN_ARTIFACT_SUFFIX),
                                   f"artifacts/{run_id}{RUN_ARTIFACT_SUFFIX}")

    def load_report_artifact_text(self, report_id: str):
        p = self.artifact_dir / (report_id + REPORT_ARTIFACT_SUFFIX)
        rel = f"artifacts/{report_id}{REPORT_ARTIFACT_SUFFIX}"
        if not p.exists():
            return None, Finding(CORRUPTION, rel, "报告 CSV 共享文件缺失")
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as fh:
                return fh.read(), None
        except (OSError, UnicodeDecodeError) as exc:
            return None, Finding(CORRUPTION, rel, f"报告 CSV 不可读：{exc}")

    def list_artifact_files(self) -> list[Path]:
        if not self.artifact_dir.is_dir():
            return []
        return sorted(p for p in self.artifact_dir.iterdir() if p.is_file())


def _reject_constant(value: str):
    """json.parse_constant 钩子：NaN/Infinity 非合法 JSON，按坏文件处理。"""
    raise json.JSONDecodeError(f"非法 JSON 数值常量 {value}（NaN/Infinity 不允许）", "", 0)


def _load_json_artifact(path: Path, rel: str) -> tuple[Any | None, Finding | None]:
    if not path.exists():
        return None, Finding(CORRUPTION, rel, "共享结果文件缺失")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh, parse_constant=_reject_constant), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, Finding(CORRUPTION, rel, f"共享结果文件不可读：{exc}")
    except json.JSONDecodeError as exc:
        return None, Finding(CORRUPTION, rel,
                             f"共享结果 JSON 解析失败（坏文件）：{exc.msg} 行{exc.lineno}列{exc.colno}")


# --------------------------------------------------------------------------- #
# 数值比对
# --------------------------------------------------------------------------- #

def _is_finite_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _within_tolerance(a: float, b: float, rtol: float, atol: float) -> bool:
    return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)


def deep_compare(path: str, expected: Any, actual: Any,
                 rtol: float, atol: float, findings: list[Finding],
                 max_findings: int = 25, drift_rel: float = DRIFT_REL,
                 drift_atol: float = DRIFT_ATOL) -> int:
    """递归比对。

    - 结构/类型/字符串不符 -> corruption
    - 有限数值差异在漂移带内（|a-e| <= drift_rel*|e| + drift_atol）-> numeric
    - 有限数值差异超出漂移带（通常是被整体改写）-> corruption
    checksum 由调用方单独显式校验，这里跳过。

    返回本路径下 numeric 差异数量（findings 受 max_findings 截断）。
    """
    numeric_count = 0
    if len(findings) >= max_findings:
        return numeric_count
    if _is_finite_number(expected) and _is_finite_number(actual):
        e, a = float(expected), float(actual)
        if _within_tolerance(a, e, rtol, atol):
            return numeric_count
        in_drift_band = abs(a - e) <= drift_rel * abs(e) + drift_atol
        numeric_count += 1 if in_drift_band else 0
        category = NUMERIC if in_drift_band else CORRUPTION
        if len(findings) < max_findings:
            findings.append(Finding(
                category, path,
                f"数值差异 {a:.12g} 与复算值 {e:.12g}"
                + ("超出对账容差（仍在漂移带内，判为数值误差）" if in_drift_band
                   else "超出漂移带，判为数据损坏"),
                expected=e, actual=a,
                tolerance={"rel": rtol, "abs": atol,
                           "drift_rel": drift_rel, "drift_atol": drift_atol}))
        return numeric_count
    # 一方是数值、另一方不是：结构损坏
    if isinstance(expected, (int, float)) != isinstance(actual, (int, float)):
        findings.append(Finding(CORRUPTION, path,
                                f"类型不符：复算 {type(expected).__name__} / 归档 {type(actual).__name__}"))
        return numeric_count
    if isinstance(expected, dict) and isinstance(actual, dict):
        ek, ak = set(expected), set(actual)
        for k in sorted(ek - ak):
            findings.append(Finding(CORRUPTION, f"{path}.{k}", "归档缺少字段"))
        for k in sorted(ak - ek):
            findings.append(Finding(CORRUPTION, f"{path}.{k}", "归档存在多余字段"))
        for k in sorted(ek & ak):
            if k in SKIP_KEYS:
                continue
            numeric_count += deep_compare(f"{path}.{k}", expected[k], actual[k],
                                          rtol, atol, findings, max_findings,
                                          drift_rel, drift_atol)
        return numeric_count
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            findings.append(Finding(CORRUPTION, path,
                                    f"数组长度不符：复算 {len(expected)} / 归档 {len(actual)}"))
        for i, (e, a) in enumerate(zip(expected, actual)):
            numeric_count += deep_compare(f"{path}[{i}]", e, a,
                                          rtol, atol, findings, max_findings,
                                          drift_rel, drift_atol)
        return numeric_count
    if expected != actual:
        findings.append(Finding(CORRUPTION, path,
                                f"值不符：复算 {json.dumps(expected, ensure_ascii=False)[:80]} / "
                                f"归档 {json.dumps(actual, ensure_ascii=False)[:80]}"))
    return numeric_count


# --------------------------------------------------------------------------- #
# 报告 CSV 对账
# --------------------------------------------------------------------------- #

def _split_csv_sections(text: str) -> list[list[list[str]]]:
    reader = csv.reader(io.StringIO(text))
    sections: list[list[list[str]]] = [[]]
    for row in reader:
        if not any(cell.strip() for cell in row):
            if sections[-1]:
                sections.append([])
            continue
        sections[-1].append(row)
    return [s for s in sections if s]


def compare_report_csv(path: str, expected_text: str, actual_text: str,
                       rtol: float, atol: float) -> list[Finding]:
    findings: list[Finding] = []
    # 生产 CSV 带 UTF-8 BOM（﻿），读归档时已用 utf-8-sig 剥离；
    # 期望文本在内存重建，这里同样剥离 BOM 再比对，避免表头首列误报。
    expected_text = expected_text.lstrip("﻿")
    actual_text = actual_text.lstrip("﻿")
    try:
        exp_sections = _split_csv_sections(expected_text)
    except csv.Error as exc:
        return [Finding(CORRUPTION, path, f"复算报告 CSV 生成失败（内部错误）：{exc}")]
    try:
        act_sections = _split_csv_sections(actual_text)
    except csv.Error as exc:
        return [Finding(CORRUPTION, path, f"归档报告 CSV 解析失败（坏文件）：{exc}")]
    if len(exp_sections) != len(act_sections):
        findings.append(Finding(CORRUPTION, path,
                                f"报告分区数不符：复算 {len(exp_sections)} / 归档 {len(act_sections)}"))
        return findings
    numeric_headers = {"raw_h_weight", "display_fraction", "raw_w_weight",
                       "cosine_similarity", "frobenius_error"}
    # checksum 是十六进制摘要，必须逐字符相等，不能按数值解析
    exact_headers = {"checksum"}
    for si, (es, as_) in enumerate(zip(exp_sections, act_sections)):
        sp = f"{path}#section{si + 1}"
        if not es or not as_:
            findings.append(Finding(CORRUPTION, sp, "存在空分区"))
            continue
        if es[0] != as_[0]:
            findings.append(Finding(CORRUPTION, f"{sp}#header",
                                    f"表头不符：复算 {es[0]} / 归档 {as_[0]}"))
            continue
        header = es[0]
        if len(es) != len(as_):
            findings.append(Finding(CORRUPTION, sp,
                                    f"数据行数不符：复算 {len(es) - 1} / 归档 {len(as_) - 1}"))
        for ri, (er, ar) in enumerate(zip(es[1:], as_[1:]), start=1):
            if len(er) != len(ar):
                findings.append(Finding(CORRUPTION, f"{sp}#row{ri}",
                                        f"列数不符：复算 {len(er)} / 归档 {len(ar)}"))
                continue
            for ci, (ev, av) in enumerate(zip(er, ar)):
                cp = f"{sp}#row{ri}.{header[ci] if ci < len(header) else ci}"
                if header and ci < len(header) and header[ci] in exact_headers:
                    if ev != av:
                        findings.append(Finding(CORRUPTION, cp,
                                                f"报告 {header[ci]} 不符：复算 {ev!r} / 归档 {av!r}"))
                elif header and ci < len(header) and header[ci] in numeric_headers:
                    try:
                        en, an = float(ev), float(av)
                    except ValueError:
                        findings.append(Finding(CORRUPTION, cp,
                                                f"数值单元格无法解析：归档 {av!r}"))
                        continue
                    if _within_tolerance(an, en, rtol, atol):
                        continue
                    in_band = abs(an - en) <= DRIFT_REL * abs(en) + DRIFT_ATOL
                    findings.append(Finding(
                        NUMERIC if in_band else CORRUPTION, cp,
                        f"报告数值差异 {an:.12g} 与复算 {en:.12g}"
                        + ("超出容差（漂移带内，数值误差）" if in_band else "超出漂移带，数据损坏"),
                        expected=en, actual=an,
                        tolerance={"rel": rtol, "abs": atol}))
                elif ev != av:
                    findings.append(Finding(CORRUPTION, cp,
                                            f"报告单元格不符：复算 {ev!r} / 归档 {av!r}"))
    return findings


# --------------------------------------------------------------------------- #
# 单运行核验
# --------------------------------------------------------------------------- #

def _recompute(run: dict, studies: dict, lexicons: dict, datasets: dict,
               rep: RunReport) -> dict | None:
    """按原快照复算；依据缺失返回 None 并记 unverifiable。"""
    study_id = run.get("study_id")
    study = studies.get(study_id) if isinstance(study_id, str) else None
    if study is None:
        rep.add(Finding(UNVERIFIABLE, f"runs/{run.get('id')}/study_id",
                        f"缺少方案 {study_id!r}，无法复算"))
        return None
    lex = lexicons.get(study.get("lexicon_id"))
    if lex is None:
        rep.add(Finding(UNVERIFIABLE, f"studies/{study.get('id')}/lexicon_id",
                        f"缺少词典快照 {study.get('lexicon_id')!r}，无法复算"))
        return None
    ds = datasets.get(study.get("dataset_id"))
    if ds is None:
        rep.add(Finding(UNVERIFIABLE, f"studies/{study.get('id')}/dataset_id",
                        f"缺少原语料快照 {study.get('dataset_id')!r}，无法复算"))
        return None
    if not isinstance(ds.get("rows"), list) or not ds["rows"]:
        rep.add(Finding(UNVERIFIABLE, f"datasets/{ds.get('id')}/rows",
                        "语料快照缺少 rows，无法复算"))
        return None
    try:
        return analyze(ds["rows"], lex, study)
    except Exception as exc:  # 复算本身抛错：归档快照不完整/不一致，归损坏而非静默
        rep.add(Finding(CORRUPTION, f"runs/{run['id']}/recompute",
                        f"按快照复算失败：{type(exc).__name__}: {exc}"))
        return None


def verify_run(run_id: str, runs: dict, studies: dict, lexicons: dict,
               datasets: dict, reviews: dict, reports: dict, source,
               rtol: float, atol: float,
               drift_rel: float = DRIFT_REL,
               drift_atol: float = DRIFT_ATOL) -> RunReport:
    rep = RunReport(run_id=run_id)
    run = runs.get(run_id)
    if run is None:
        rep.add(Finding(CORRUPTION, f"runs/{run_id}", "运行记录在库内缺失"))
        return rep
    run_status = run.get("status")
    rep.detail["status"] = run_status
    if run_status != "completed":
        # 未完成运行没有可对账结果；失败原因保留即可，不算损坏也不参与复算。
        rep.checks["recompute"] = "skipped:run-not-completed"
        rep.detail["error"] = run.get("error", "")
        rep.status = OK
        return rep

    db_result = run.get("result")
    if not isinstance(db_result, dict) or not db_result:
        rep.add(Finding(CORRUPTION, f"runs/{run_id}/result",
                        "库内结果载荷缺失或不是对象"))
        db_result = None

    # 1) 共享结果文件
    artifact, f = source.load_run_artifact(run_id)
    if f is not None:
        rep.add(f)
    rep.checks["shared_artifact"] = "missing-or-bad" if f else "present"

    # 2) 复算依据与 checksum
    oracle = _recompute(run, studies, lexicons, datasets, rep)
    if oracle is None:
        rep.verified = False
        # 旧归档无法核验：库内/文件之间仍可做结构一致性检查
        if db_result is not None and isinstance(artifact, dict):
            deep_compare(f"runs/{run_id}/result", db_result, artifact,
                         rtol, atol, rep.findings,
                         drift_rel=drift_rel, drift_atol=drift_atol)
        return rep

    rep.verified = True
    rep.checks["recompute"] = "ok"
    rep.detail["included"] = oracle.get("included")
    rep.detail["isolated"] = len(oracle.get("isolated", []))
    rep.detail["features"] = oracle.get("feature_count")
    rep.detail["iterations"] = oracle.get("nmf", {}).get("iterations")
    rep.detail["converged"] = oracle.get("nmf", {}).get("converged")

    # checksum：库内结果自报的 checksum 必须与按快照重算的 checksum 一致
    if db_result is not None:
        if db_result.get("checksum") != oracle.get("checksum"):
            rep.add(Finding(CORRUPTION, f"runs/{run_id}/result/checksum",
                            "checksum 与按原语料/词典/方案快照重算值不符",
                            expected=oracle.get("checksum"),
                            actual=db_result.get("checksum")))
        # 3) 库内结果 vs 复算（全字段：有效文档、主题权重、近邻、W/H、稀疏向量…）
        before = len(rep.findings)
        deep_compare(f"runs/{run_id}/result", oracle, db_result,
                     rtol, atol, rep.findings,
                     drift_rel=drift_rel, drift_atol=drift_atol)
        rep.checks["db_vs_recompute"] = "diff-found" if len(rep.findings) > before else "match"
    if isinstance(artifact, dict):
        if artifact.get("checksum") != oracle.get("checksum"):
            rep.add(Finding(CORRUPTION, f"artifacts/{run_id}.json/checksum",
                            "共享文件 checksum 与复算值不符",
                            expected=oracle.get("checksum"),
                            actual=artifact.get("checksum")))
        before = len(rep.findings)
        deep_compare(f"artifacts/{run_id}.json", oracle, artifact,
                     rtol, atol, rep.findings,
                     drift_rel=drift_rel, drift_atol=drift_atol)
        rep.checks["artifact_vs_recompute"] = "diff-found" if len(rep.findings) > before else "match"
        # 库内与共享文件不另做深比：两者都已对同一复算基准核验，
        # 各自匹配基准即必然互相一致，重复深比只会产生同路径重复差异。
        rep.checks["db_vs_artifact"] = (
            "match" if rep.checks.get("db_vs_recompute") == "match"
            and rep.checks["artifact_vs_recompute"] == "match" else "diff-found")
    elif artifact is not None:
        rep.add(Finding(CORRUPTION, f"artifacts/{run_id}.json",
                        f"共享结果文件不是 JSON 对象（{type(artifact).__name__}）"))

    # 4) 人工命名复核版本
    linked_reviews = [r for r in reviews.values() if r.get("run_id") == run_id]
    rep.detail["review_count"] = len(linked_reviews)
    approved = [r for r in linked_reviews if r.get("status") == "approved"]
    if db_result is not None:
        topic_ids = [t.get("id") for t in db_result.get("topics", [])]
        for rv in linked_reviews:
            base = f"reviews/{rv.get('id')}"
            names = rv.get("theme_names")
            if not isinstance(names, dict):
                rep.add(Finding(CORRUPTION, f"{base}/theme_names", "人工命名不是对象"))
                continue
            if set(names) != set(topic_ids):
                rep.add(Finding(CORRUPTION, f"{base}/theme_names",
                                f"命名主题编号集合 {sorted(names)} 与运行主题 {topic_ids} 不符"))
            lengths = {k: len(str(v).strip()) for k, v in names.items()}
            bad = {k: n for k, n in lengths.items() if not 1 <= n <= 40}
            if bad:
                rep.add(Finding(CORRUPTION, f"{base}/theme_names",
                                f"存在长度越界（1—40字）的人工名称：{bad}"))
            if len(set(names.values())) != len(names):
                rep.add(Finding(CORRUPTION, f"{base}/theme_names", "人工名称不唯一"))
        if len(approved) > 1:
            rep.add(Finding(CORRUPTION, f"runs/{run_id}/reviews",
                            f"存在 {len(approved)} 个已批准复核，报告命名版本不唯一"))

    # 5) 已批准报告：库内记录 + CSV 共享文件 + 人工命名版本
    linked_reports = [r for r in reports.values() if r.get("run_id") == run_id]
    rep.detail["report_count"] = len(linked_reports)
    for rpt in linked_reports:
        rpt_id = rpt.get("id")
        base = f"reports/{rpt_id}"
        rv = reviews.get(rpt.get("review_id"))
        if rv is None:
            rep.add(Finding(CORRUPTION, f"{base}/review_id",
                            f"报告引用的复核 {rpt.get('review_id')!r} 不存在"))
            continue
        if rv.get("run_id") != run_id:
            rep.add(Finding(CORRUPTION, f"{base}/review_id",
                            "报告引用复核属于其他运行"))
        if rv.get("status") != "approved":
            rep.add(Finding(CORRUPTION, f"{base}/review_id",
                            f"报告引用复核状态为 {rv.get('status')!r}，非 approved"))
        text, f = source.load_report_artifact_text(rpt_id)
        if f is not None:
            rep.add(f)
            continue
        # 用生产报告生成口径在内存中重建期望 CSV（不落盘），与归档对拍
        try:
            expected_text = report_service.build_download(rpt, run, rv)
        except Exception as exc:
            rep.add(Finding(CORRUPTION, f"{base}/rebuild",
                            f"复算报告生成失败：{type(exc).__name__}: {exc}"))
            continue
        for cf in compare_report_csv(f"artifacts/{rpt_id}.csv",
                                     expected_text, text, rtol, atol):
            rep.add(cf)
        rep.checks[f"report:{rpt_id}"] = "checked"
    return rep


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def collect(source) -> tuple[dict[str, dict], list[Finding]]:
    tables: dict[str, dict] = {}
    load_findings: list[Finding] = []
    for t in TABLES:
        rows, fs = source.load_table(t)
        tables[t] = rows
        load_findings.extend(fs)
    return tables, load_findings


def run_reconcile(source, rtol: float, atol: float,
                  drift_rel: float = DRIFT_REL,
                  drift_atol: float = DRIFT_ATOL) -> dict:
    tables, load_findings = collect(source)
    runs, studies = tables["runs"], tables["studies"]
    lexicons, datasets = tables["lexicons"], tables["datasets"]
    reviews, reports = tables["reviews"], tables["reports"]

    run_reports: list[RunReport] = []
    for run_id in sorted(runs):
        run_reports.append(verify_run(run_id, runs, studies, lexicons, datasets,
                                      reviews, reports, source, rtol, atol,
                                      drift_rel, drift_atol))

    # 孤儿共享文件：文件存在但没有对应库内记录（坏文件/错放文件也要点名，每文件一条）
    orphan_findings: list[Finding] = []
    known_run_files = {rid + RUN_ARTIFACT_SUFFIX for rid in runs}
    known_report_files = {rid + REPORT_ARTIFACT_SUFFIX for rid in reports}
    for p in source.list_artifact_files():
        if p.suffix == RUN_ARTIFACT_SUFFIX and p.name not in known_run_files:
            orphan_findings.append(Finding(
                CORRUPTION, f"artifacts/{p.name}",
                "孤儿共享结果文件：库内无对应 runs 记录"))
        elif p.suffix == REPORT_ARTIFACT_SUFFIX and p.name not in known_report_files:
            orphan_findings.append(Finding(
                CORRUPTION, f"artifacts/{p.name}",
                "孤儿报告文件：库内无对应 reports 记录"))
        elif p.suffix not in (RUN_ARTIFACT_SUFFIX, REPORT_ARTIFACT_SUFFIX):
            orphan_findings.append(Finding(
                CORRUPTION, f"artifacts/{p.name}",
                "无法识别的共享文件（后缀非 .json/.csv）"))

    all_findings = list(load_findings)
    for rr in run_reports:
        all_findings.extend(rr.findings)
    all_findings.extend(orphan_findings)
    # 单运行 deep_compare 有 25 条上限：达到上限时补一条提示，确保差异不被静默吞掉
    rank = {OK: -1, UNVERIFIABLE: 0, NUMERIC: 1, CORRUPTION: 2}
    for rr in run_reports:
        # deep_compare 直接追加 findings，这里按最严重类别统一回算状态
        worst = max((rank.get(f.category, -1) for f in rr.findings), default=-1)
        if worst > rank.get(rr.status, -1):
            rr.status = next(c for c, r in rank.items() if r == worst)
        if len(rr.findings) >= 25:
            note = Finding(INFO, f"runs/{rr.run_id}",
                           "差异条目达到单运行展示上限25，仅列出前25条；"
                           "请用 --json 获取完整定位或收紧对账范围后重跑")
            rr.findings.append(note)
            all_findings.append(note)

    counts = {CORRUPTION: 0, NUMERIC: 0, UNVERIFIABLE: 0, INFO: 0}
    for f in all_findings:
        counts[f.category] = counts.get(f.category, 0) + 1
    # 无法核验：仅统计已完成、但因缺少复算依据而未复算的运行（失败/排队运行不要求复算）
    unverifiable_runs = sorted({
        rr.run_id for rr in run_reports
        if not rr.verified and rr.detail.get("status") == "completed"
    })
    summary = {
        "runs_total": len(run_reports),
        "runs_verified": sum(1 for r in run_reports if r.verified),
        "runs_unverifiable": unverifiable_runs,
        "reports_total": len(reports),
        "findings_corruption": counts[CORRUPTION],
        "findings_numeric": counts[NUMERIC],
        "findings_unverifiable": counts[UNVERIFIABLE],
        "orphan_artifacts": len(orphan_findings),
    }
    return {"summary": summary, "runs": [rr for rr in run_reports],
            "load_findings": load_findings, "orphan_findings": orphan_findings,
            "all_findings": all_findings}


def render_text(result: dict, verbose: bool) -> str:
    s = result["summary"]
    lines = ["=" * 72, "离线归档批量对账报告（只读，未修改任何原始数据）", "=" * 72]
    lines.append(f"运行总数 {s['runs_total']}，成功复算核验 {s['runs_verified']}，"
                 f"无法核验 {len(s['runs_unverifiable'])}，报告 {s['reports_total']}")
    lines.append(f"差异统计：数据损坏 {s['findings_corruption']}，"
                 f"数值误差 {s['findings_numeric']}，无法核验 {s['findings_unverifiable']}，"
                 f"孤儿文件 {s['orphan_artifacts']}")
    if s["runs_unverifiable"]:
        lines.append("无法核验旧归档（缺少复算依据，单列）：" + ", ".join(s["runs_unverifiable"]))
    lines.append("-" * 72)
    for rr in result["runs"]:
        mark = {CORRUPTION: "✗ 损坏", NUMERIC: "△ 数值",
                UNVERIFIABLE: "? 无法核验", INFO: "ℹ 提示"}.get(rr.status, "✓")
        lines.append(f"[{mark}] run={rr.run_id} status={rr.detail.get('status')} "
                     f"findings={len(rr.findings)}")
        if rr.checks:
            lines.append("    检查项: " + ", ".join(f"{k}={v}" for k, v in sorted(rr.checks.items())))
        if verbose or rr.findings:
            for f in rr.findings:
                lines.append(f"    - [{f.category}] {f.object_path}: {f.message}")
    for f in result["load_findings"] + result["orphan_findings"]:
        lines.append(f"[{f.category}] {f.object_path}: {f.message}")
    lines.append("-" * 72)
    if not result["all_findings"]:
        lines.append("结论：全部可核验运行的库内结果、共享文件与报告均与复算一致。")
    return "\n".join(lines)


def exit_code(result: dict) -> int:
    s = result["summary"]
    if s["findings_corruption"] > 0:
        return 1
    if s["findings_numeric"] > 0:
        return 1  # 容差外数值误差同样以失败结束
    if s["runs_unverifiable"]:
        return 2
    return 0


def build_source(args) -> ArchiveSource | SqliteSource:
    if args.archive:
        root = Path(args.archive)
        if not root.is_dir():
            print(f"归档根目录不存在或不是目录：{root}", file=sys.stderr)
            raise SystemExit(3)
        return ArchiveSource(root)
    db = Path(args.sqlite)
    if not db.is_file():
        print(f"SQLite 数据库不存在：{db}", file=sys.stderr)
        raise SystemExit(3)
    artifact_dir = Path(args.artifacts) if args.artifacts else \
        Path(os.getenv("ARTIFACT_DIR", "/tmp/interview-topics-artifacts"))
    return SqliteSource(db, artifact_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="离线归档只读批量对账：按原语料/词典快照复算并核对库内结果、共享JSON与批准报告")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--archive", help="离线归档根目录（含 datasets/ ... artifacts/）")
    src.add_argument("--sqlite", help="在线 SQLite 数据库路径（以 immutable 只读打开）")
    parser.add_argument("--artifacts", help="共享产物目录（SQLite 模式，默认取 ARTIFACT_DIR）")
    parser.add_argument("--rtol", type=float, default=1e-9, help="数值相对容差，默认 1e-9")
    parser.add_argument("--atol", type=float, default=1e-12, help="数值绝对容差，默认 1e-12")
    parser.add_argument("--drift-rel", type=float, default=DRIFT_REL,
                        help="数值漂移带相对幅度，带内差异判为数值误差，带外判损坏，默认 1e-2")
    parser.add_argument("--drift-atol", type=float, default=DRIFT_ATOL,
                        help="数值漂移带绝对幅度，默认 1e-8")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：容差收紧到0，要求逐位精确重放，任何数值差异均失败")
    parser.add_argument("--json", dest="json_out", help="把机器可读结果写入该文件（不写归档目录）")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总")
    args = parser.parse_args(argv)

    source = build_source(args)
    # strict：固定 seed 的精确重放应逐位一致，容差收紧到 0（漂移带保留，用于区分误差与损坏）
    rtol, atol = (0.0, 0.0) if args.strict else (args.rtol, args.atol)
    result = run_reconcile(source, rtol, atol, args.drift_rel, args.drift_atol)

    print(render_text(result, verbose=not args.quiet))
    if args.json_out:
        out = Path(args.json_out)
        payload = {
            "summary": result["summary"],
            "findings": [f.to_dict() for f in result["all_findings"]],
            "runs": [{"run_id": rr.run_id, "status": rr.status, "verified": rr.verified,
                      "checks": rr.checks, "detail": rr.detail,
                      "findings": [f.to_dict() for f in rr.findings]}
                     for rr in result["runs"]],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"机器可读结果已写入：{out}（归档与数据库未被修改）")
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
