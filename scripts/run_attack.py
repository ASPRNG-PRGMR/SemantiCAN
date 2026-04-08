"""
Manually trigger attack ECU injection against a running backend.

Because the bus is in-process, this script is most useful when you want
to start an attack without the 10-second auto-delay that main.py uses.

Usage — run from the project root WHILE the backend is already running:
    python scripts/run_attack.py

Note: this spins up its own bus instance and publishes to it directly,
which works if main.py's subscription is on a shared bus. For a true
shared-bus attack trigger, use the sim.yaml `attack_start_after` setting
or modify main.py to accept a signal.

For a self-contained demo you can simply lower `attack_start_after` in
backend/sim/sim.yaml to 0.
"""
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.sim.bus import MessageBus
from backend.sim.node_attack import start_attack_node

if __name__ == "__main__":
    print("[!] Launching standalone attack node…")
    print("    NOTE: This uses a separate bus instance.")
    print("    To inject into a live run, lower attack_start_after in sim.yaml.")
    bus = MessageBus()
    start_attack_node(bus)   # blocks forever
