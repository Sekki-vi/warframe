#!/usr/bin/env python3
"""Run tests/test_knowledge_retrieval.py regression suite."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    rc = subprocess.call([sys.executable, str(PROJECT_ROOT / "tests" / "test_knowledge_retrieval.py"), "-v"])
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
