"""
Demonstrates the actual gap the Consistency Engine closes (TARA-05):

Runs the stealthy coordinated attack (backend/sim/node_stealth.py) through
the REAL detection pipeline — same FeatureExtractor, same semantic_checks,
same score_violations used live in backend/main.py — and reports, side by
side:

  1. Did any existing per-ECU rule fire on any stealth message?  (expect: NO)
  2. Did the Consistency Engine fire?                            (expect: YES)

This is the evidence for the claim in Detection.md / TARA.md that TARA-05
("rule threshold blind spots") is a real, closeable gap, not a hypothetical
one — it isolates the stealth attack from the normal/blatant-attack traffic
so the result is unambiguous.

Usage (from project root):
    python scripts/evaluate_consistency.py --duration 12
"""

import argparse
import sys
import time
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus import MessageBus
from backend.sim.node_normal import start_normal_node
from backend.sim.node_stealth import start_stealth_node
from backend.core.features import FeatureExtractor
from backend.core.checks import semantic_checks
from backend.core.scoring import score_violations
from backend.core.consistency import ConsistencyEngine


def main():
    parser = argparse.ArgumentParser(description="Demonstrate Consistency Engine catching a stealth cross-ECU attack")
    parser.add_argument("--duration", type=float, default=12.0, help="How long to run, in seconds")
    parser.add_argument("--stealth-delay", type=float, default=3.0, help="Seconds of normal-only baseline before stealth attack starts")
    args = parser.parse_args()

    bus = MessageBus()
    detection_queue = bus.subscribe("vehicle_state")
    extractor = FeatureExtractor()
    consistency_engine = ConsistencyEngine()

    Thread(target=start_normal_node, args=(bus,), daemon=True).start()

    def _delayed_stealth():
        time.sleep(args.stealth_delay)
        start_stealth_node(bus)

    Thread(target=_delayed_stealth, daemon=True).start()

    per_ecu_rule_fires_on_stealth_ecus = []
    consistency_findings_seen = []

    stealth_ecu_ids = {"ECU_SPEED", "ECU_BRAKE", "ECU_STEER"}

    print(f"[*] Running for {args.duration}s (stealth attack starts at t={args.stealth_delay}s) ...")
    t_start = time.time()
    while time.time() - t_start < args.duration:
        try:
            ts, message = detection_queue.get(timeout=0.5)
        except Exception:
            continue

        node_id = message.get("node_id", "UNKNOWN")
        features = extractor.extract(ts, message)
        violations = semantic_checks(message, features)

        # Only meaningful once the stealth attack has started — before that,
        # these node_ids simply aren't publishing at all.
        if node_id in stealth_ecu_ids and violations:
            per_ecu_rule_fires_on_stealth_ecus.append({
                "t": round(time.time() - t_start, 2),
                "node_id": node_id,
                "violations": violations,
            })

        findings = consistency_engine.process(node_id, ts, message)
        if findings:
            _, conf = score_violations(findings)
            consistency_findings_seen.append({
                "t": round(time.time() - t_start, 2),
                "findings": [f["type"] for f in findings],
                "confidence": conf,
            })

    print("\n=== Result ===")
    print(f"Per-ECU rule fires on ECU_SPEED/ECU_BRAKE/ECU_STEER during stealth window: "
          f"{len(per_ecu_rule_fires_on_stealth_ecus)}")
    for e in per_ecu_rule_fires_on_stealth_ecus[:5]:
        print(f"    t={e['t']}s  {e['node_id']}  {e['violations']}")

    print(f"\nConsistency Engine findings: {len(consistency_findings_seen)}")
    for f in consistency_findings_seen[:5]:
        print(f"    t={f['t']}s  {f['findings']}  confidence={f['confidence']}")

    print("\n=== Conclusion ===")
    if not per_ecu_rule_fires_on_stealth_ecus and consistency_findings_seen:
        print("Existing per-ECU rules: 0 detections on a sustained, coordinated attack.")
        print("Consistency Engine: detected it. This is the TARA-05 gap, closed.")
    elif per_ecu_rule_fires_on_stealth_ecus:
        print("NOTE: per-ECU rules fired on the stealth attack — the payload needs")
        print("further tuning to stay under every existing threshold (check thresholds")
        print("in backend/core/checks.py against backend/sim/node_stealth.py's values).")
    else:
        print("NOTE: Consistency Engine did not fire — check timing/thresholds in")
        print("backend/core/consistency.py against --duration and --stealth-delay.")


if __name__ == "__main__":
    main()
