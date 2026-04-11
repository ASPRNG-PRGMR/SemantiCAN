"""Convenience launcher — run from project root: python scripts/run_backend.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backend.main   # noqa: F401  (executes the module)
