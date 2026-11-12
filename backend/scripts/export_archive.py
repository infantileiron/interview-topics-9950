# -*- coding: utf-8 -*-
"""把在线库（SQLite/PostgreSQL）与共享产物只读导出为离线归档目录。

导出目标必须是不存在或完全为空的新目录；脚本对源库只执行 SELECT，
不调用任何写接口，共享产物按字节复制。导出后的目录可直接交给
scripts.reconcile_archive 批量对账。

用法：
  python -m scripts.export_archive --sqlite /tmp/interview-topics.sqlite \
      --artifacts /tmp/interview-topics-artifacts --out /tmp/archive-2026-11
  DATABASE_URL=postgresql://... python -m scripts.export_archive \
      --artifacts /artifacts --out /tmp/archive-2026-11
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TABLES = ("datasets", "lexicons", "studies", "runs", "reviews", "reports")


def _read_sqlite(db_path: Path) -> dict[str, dict]:
    uri = f"file:{db_path.resolve()}?immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        out = {}
        for table in TABLES:
            rows = conn.execute(f"SELECT payload FROM {table} ORDER BY id").fetchall()
            out[table] = {json.loads(r[0])["id"]: json.loads(r[0]) for r in rows}
        return out
    finally:
        conn.close()


def _read_pg(database_url: str) -> dict[str, dict]:
    import psycopg
    # 在连接层声明只读默认事务，整个导出只允许 SELECT
    sep = "&" if "?" in database_url else "?"
    conn = psycopg.connect(f"{database_url}{sep}default_transaction_read_only=1")
    try:
        conn.execute("SET TRANSACTION READ ONLY")
        out = {}
        for table in TABLES:
            rows = conn.execute(f"SELECT payload FROM {table} ORDER BY id").fetchall()
            out[table] = {json.loads(r[0])["id"]: json.loads(r[0]) for r in rows}
        return out
    finally:
        conn.close()


def export(out_dir: Path, tables: dict[str, dict], artifact_dir: Path) -> dict:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"导出目标必须是不存在或空目录：{out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table in TABLES:
        td = out_dir / table
        td.mkdir()
        for _id, payload in tables[table].items():
            (td / f"{_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        counts[table] = len(tables[table])
    art_out = out_dir / "artifacts"
    art_out.mkdir(exist_ok=True)
    copied = 0
    if artifact_dir.is_dir():
        for p in sorted(artifact_dir.iterdir()):
            if p.is_file() and p.suffix in (".json", ".csv"):
                shutil.copyfile(p, art_out / p.name)  # 源只读、目标为新目录
                copied += 1
    counts["artifacts"] = copied
    manifest = {
        "note": "只读导出；源库仅 SELECT，共享产物按字节复制",
        "tables": counts,
    }
    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读导出离线归档目录")
    parser.add_argument("--out", required=True, help="导出目标（不存在或空目录）")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--sqlite", help="SQLite 数据库路径（immutable 只读打开）")
    src.add_argument("--database-url", default=os.getenv("DATABASE_URL"),
                     help="PostgreSQL DSN（默认取环境变量 DATABASE_URL）")
    parser.add_argument("--artifacts", required=True, help="共享产物目录")
    args = parser.parse_args(argv)

    if args.sqlite:
        db = Path(args.sqlite)
        if not db.is_file():
            raise SystemExit(f"数据库不存在：{db}")
        tables = _read_sqlite(db)
    elif args.database_url:
        tables = _read_pg(args.database_url)
    else:
        raise SystemExit("必须提供 --sqlite 或 --database-url（或设置 DATABASE_URL）")

    counts = export(Path(args.out), tables, Path(args.artifacts))
    print("导出完成（源数据未修改）：")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
