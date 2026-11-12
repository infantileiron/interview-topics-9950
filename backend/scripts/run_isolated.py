# -*- coding: utf-8 -*-
"""隔离模式引导器：配合 python -I 使用。

用途：对不可信离线归档执行对账时，用 -I 屏蔽归档目录可能植入的 json.py 等
同名模块；第三方依赖（numpy 等）与后端代码路径通过环境变量显式注入 sys.path，
不依赖 PYTHONPATH（-I 会忽略它），也不把归档目录加入模块搜索路径。

环境变量：
  RECON_DEPS   第三方依赖目录（如含 numpy 的独立前缀），冒号分隔多个
  RECON_TARGET 要运行的脚本路径（默认 scripts/reconcile_archive.py）

示例：
  RECON_DEPS=/opt/recon-deps python3 -I scripts/run_isolated.py \
      --archive /data/archive-2026-11
"""
import os
import runpy
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

for p in reversed(os.getenv("RECON_DEPS", "").split(os.pathsep)):
    if p and p not in sys.path:
        sys.path.insert(0, p)
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

target = os.getenv("RECON_TARGET") or str(
    BACKEND_ROOT / "scripts" / "reconcile_archive.py")
sys.argv = [target] + sys.argv[1:]
runpy.run_path(target, run_name="__main__")
