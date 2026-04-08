"""
Launch the Dash frontend dashboard.
The backend must be running first (scripts/run_backend.py).
Run from the project root:
    python scripts/run_dashboard.py
"""
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
subprocess.run(
    [sys.executable, "-m", "frontend.dashboard.app"],
    cwd=str(project_root),
)
