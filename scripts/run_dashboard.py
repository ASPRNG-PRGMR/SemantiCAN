"""Convenience launcher — run from project root: python scripts/run_dashboard.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.dashboard.app import start_dashboard

if __name__ == "__main__":
    print("[*] Dashboard starting on http://127.0.0.1:8050")
    start_dashboard(debug=False)
