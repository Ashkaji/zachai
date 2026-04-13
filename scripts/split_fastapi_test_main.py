#!/usr/bin/env python3
"""Legacy one-shot: split test_main.py into test_api_sec_*.py (already applied in this repo)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "src/api/fastapi/test_main.py").exists():
    raise SystemExit(
        "test_main.py not found — split already done. "
        "Gateway tests live in src/api/fastapi/test_api_sec_*.py + fastapi_test_app.py."
    )
print("Run the historical splitter body from git history if you truly need to re-split.")
