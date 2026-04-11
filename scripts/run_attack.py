"""
Manually inject a one-shot attack payload for testing.
Usage: python scripts/run_attack.py
(Backend must be running first.)
"""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.sim.bus        import MessageBus
from backend.sim.node_attack import ATTACK_ECUS

bus = MessageBus()

print("[*] Injecting one-shot attack payloads ...")
for ecu in ATTACK_ECUS:
    msg = {"node_id": ecu["node_id"], **ecu["payload"]()}
    bus.publish("vehicle_state", msg)
    print(f"  → {msg}")

print("[*] Done.")
