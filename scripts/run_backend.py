"""
Launch the backend: ECU simulation + semantic detection engine + Flask API.
Run from the project root:
    python scripts/run_backend.py
"""
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
subprocess.run(
    [sys.executable, "-m", "backend.main"],
    cwd=str(project_root),
)
