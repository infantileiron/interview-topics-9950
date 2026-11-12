# -*- coding: utf-8 -*-
"""生成离线归档对账测试夹具（只写 --out 指定的全新目录，不碰仓库源码）。

场景：
  run-ok        正常归档（应完全核验通过）
  run-tamper    库内结果被改坏（结构损坏：文档权重/主题词/近邻被替换）
  run-drift     库内 W 权重被微小篡改（数值误差：超容差但非结构问题）
  run-badjson   共享 JSON 是坏文件（JSON 解析失败）
  run-missing   共享 JSON 缺失 + 报告 CSV 缺失
  run-old       缺少语料快照（无法核验的旧归档）
  run-badreport 报告 CSV 人工名称被替换（报告命名版本损坏）
另外放置一个孤儿共享文件。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from src.services.seed import demo_rows  # noqa: E402
from src.services.statistics import analyze  # noqa: E402
from src.services import report as report_service  # noqa: E402

TABLES = ("datasets", "lexicons", "studies", "runs", "reviews", "reports")


def _write_table(root: Path, table: str, payload: dict) -> None:
    d = root / table
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{payload['id']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_entities(suffix: str):
    rows = demo_rows()
    from src.services.seed import POOLS, STOP
    lexicon = {"id": f"lexicon-{suffix}", "name": "测试词表", "version": f"2026.11-{suffix}",
               "terms": [x for p in POOLS for x in p] + STOP, "stopwords": STOP,
               "created_at": "2026-11-01T00:00:00+00:00"}
    study = {"id": f"study-{suffix}", "name": "测试方案", "dataset_id": f"ds-{suffix}",
             "lexicon_id": lexicon["id"], "topic_count": 6, "max_iter": 250,
             "tolerance": 0.00001, "seed": 2305,
             "created_at": "2026-11-01T00:00:00+00:00"}
    dataset = {"id": f"ds-{suffix}", "name": "测试语料", "source": "fixture.csv",
               "rows": rows, "created_at": "2026-11-01T00:00:00+00:00"}
    result = analyze(rows, lexicon, study)
    names = {f"T{i+1:02d}": f"人工议题{['一', '二', '三', '四', '五', '六'][i]}"
             for i in range(6)}
    review = {"id": f"review-{suffix}", "run_id": f"run-{suffix}",
              "comment": "夹具复核命名依据，满足最少五个字。", "theme_names": names,
              "status": "approved", "reviewer": "admin@liwen.test",
              "created_at": "2026-11-02T00:00:00+00:00"}
    run = {"id": f"run-{suffix}", "study_id": study["id"], "status": "completed",
           "result": result, "error": "",
           "created_at": "2026-11-01T01:00:00+00:00"}
    rpt = {"id": f"rpt-{suffix}", "run_id": run["id"], "review_id": review["id"],
           "title": f"夹具报告 {suffix}", "created_at": "2026-11-03T00:00:00+00:00"}
    csv_text = report_service.build_download(rpt, run, review)
    return dataset, lexicon, study, run, review, rpt, csv_text


def _materialize(root: Path, dataset, lexicon, study, run, review, rpt, csv_text,
                 write_dataset=True):
    if write_dataset:
        _write_table(root, "datasets", dataset)
    _write_table(root, "lexicons", lexicon)
    _write_table(root, "studies", study)
    _write_table(root, "runs", run)
    _write_table(root, "reviews", review)
    _write_table(root, "reports", rpt)
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / f"{run['id']}.json").write_text(
        json.dumps(run["result"], ensure_ascii=False), encoding="utf-8")
    (art / f"{rpt['id']}.csv").write_text(csv_text, encoding="utf-8")


def build(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"夹具目录必须为空：{out}")
    out.mkdir(parents=True)

    # 1) 正常
    _materialize(out, *_base_entities("ok"))

    # 2) 库内结果结构损坏（改 W、主题词、近邻）
    ds, lex, study, run, review, rpt, csv_text = _base_entities("tamper")
    bad = json.loads(json.dumps(run["result"]))  # 深拷贝
    bad["documents"][0]["weights"][0] = 999.0
    bad["topics"][0]["top_terms"][0]["term"] = "被篡改的词"
    bad["neighbors"][0]["neighbors"][0]["doc_id"] = "LW-9999"
    bad["checksum"] = "deadbeef" * 8
    run["result"] = bad
    _materialize(out, ds, lex, study, run, review, rpt, csv_text)

    # 3) 数值漂移（库内 W 微调约 0.1%，超默认 1e-9 容差但在漂移带内 -> 数值误差）
    ds, lex, study, run, review, rpt, csv_text = _base_entities("drift")
    correct_result = json.loads(json.dumps(run["result"]))  # 共享文件保留正确版本
    drifted = json.loads(json.dumps(run["result"]))
    # 选一个数量级正常的权重（避免挑到接近0的权重导致相对漂移超带）
    w0 = drifted["nmf"]["w"][0]
    idx = max(range(len(w0)), key=lambda k: abs(w0[k]))
    drifted["nmf"]["w"][0][idx] = w0[idx] * (1 + 1e-3)
    run["result"] = drifted
    _materialize(out, ds, lex, study, run, review, rpt, csv_text)
    (out / "artifacts" / f"{run['id']}.json").write_text(
        json.dumps(correct_result, ensure_ascii=False), encoding="utf-8")

    # 4) 共享 JSON 坏文件
    ds, lex, study, run, review, rpt, csv_text = _base_entities("badjson")
    _materialize(out, ds, lex, study, run, review, rpt, csv_text)
    (out / "artifacts" / f"{run['id']}.json").write_text(
        '{"documents": [BROKEN,,,', encoding="utf-8")

    # 5) 共享文件与报告 CSV 缺失
    ds, lex, study, run, review, rpt, csv_text = _base_entities("missing")
    _materialize(out, ds, lex, study, run, review, rpt, csv_text)
    (out / "artifacts" / f"{run['id']}.json").unlink()
    (out / "artifacts" / f"{rpt['id']}.csv").unlink()

    # 6) 旧归档：缺语料快照 -> 无法核验
    ds, lex, study, run, review, rpt, csv_text = _base_entities("old")
    _materialize(out, ds, lex, study, run, review, rpt, csv_text, write_dataset=False)

    # 7) 报告 CSV 人工命名被替换
    ds, lex, study, run, review, rpt, csv_text = _base_entities("badreport")
    _materialize(out, ds, lex, study, run, review, rpt, csv_text)
    bad_csv = csv_text.replace(review["theme_names"]["T01"], "未授权替换名称X")
    (out / "artifacts" / f"{rpt['id']}.csv").write_text(bad_csv, encoding="utf-8")

    # 8) 孤儿共享文件
    (out / "artifacts" / "run-ghost.json").write_text(
        json.dumps({"ghost": True}), encoding="utf-8")

    print(f"夹具已生成：{out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    build(Path(args.out))
