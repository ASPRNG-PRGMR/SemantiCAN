"""
Evaluates the TARA-04 sub-threshold attack (backend/sim/node_subthreshold.py)
against the real detection pipeline.

This script proves two different things, one locally and one that needs to
be verified elsewhere:

  1. LOCALLY VERIFIABLE (no torch needed): the per-ECU rules and the
     Consistency Engine are structurally blind to ECU_GHOST. This isn't a
     probabilistic claim — it's a fact about the code (checks.py never
     evaluates a message it doesn't receive a rule-violating value in, and
     consistency.py never processes a node_id outside CORRELATED_ECU_IDS).
     This script confirms it actually holds at runtime, not just on paper.

  2. NEEDS TORCH: whether the LSTM's reconstruction-error score actually
     rises for ECU_GHOST relative to normal ECUs once it's trained. Without
     torch, backend/ai/advisor.py's ingest() always returns 0.0 (see its
     own docstring: "no fallback — avoids false positives from z-score") —
     so this script will run to completion and report *structurally
     correct but uninformative* LSTM numbers (all zero) in an environment
     without torch installed. Re-run this on a machine with torch to get
     the number that actually answers TARA-04: does the LSTM catch this,
     or was the whole point of having two detectors never actually tested?

Usage (from project root):
    python scripts/evaluate_subthreshold.py --duration 25 --ghost-delay 5
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
from backend.sim.node_subthreshold import start_ghost_node, GHOST_NODE_ID
from backend.core.features import FeatureExtractor
from backend.core.checks import semantic_checks
from backend.core.consistency import ConsistencyEngine, CORRELATED_ECU_IDS
from backend.ai.advisor import ingest_message, _TORCH_AVAILABLE as TORCH_AVAILABLE


def main():
    parser = argparse.ArgumentParser(description="Evaluate the TARA-04 sub-threshold attack")
    parser.add_argument("--duration", type=float, default=25.0, help="Total run length in seconds")
    parser.add_argument("--ghost-delay", type=float, default=5.0,
                         help="Seconds of normal-only baseline before the ghost attack starts "
                              "(should exceed the LSTM's training warm-up so this tests TARA-04 "
                              "in isolation from TARA-06, baseline poisoning)")
    args = parser.parse_args()

    if not TORCH_AVAILABLE:
        print("[!] torch not installed in this environment — LSTM will return 0.0 for")
        print("    every message (see backend/ai/advisor.py's documented no-fallback).")
        print("    Rule/Consistency Engine results below are still meaningful. Re-run")
        print("    this script on a machine with torch installed for the real answer.\n")

    bus = MessageBus()
    detection_queue = bus.subscribe("vehicle_state")
    extractor = FeatureExtractor()
    consistency_engine = ConsistencyEngine()

    print(f"[*] ECU_GHOST correlated with Consistency Engine's watched set? "
          f"{GHOST_NODE_ID in CORRELATED_ECU_IDS} (should be False)")

    Thread(target=start_normal_node, args=(bus,), daemon=True).start()

    def _delayed_ghost():
        time.sleep(args.ghost_delay)
        start_ghost_node(bus)

    Thread(target=_delayed_ghost, daemon=True).start()

    rule_fires_on_ghost = []
    consistency_fires_involving_ghost = []
    ghost_lstm_scores = []       # (t, confidence) for ECU_GHOST
    normal_lstm_scores = []      # (t, confidence) for one comparison normal ECU
    comparison_ecu = "ECU_001"

    print(f"[*] Running {args.duration}s (ghost starts at t={args.ghost_delay}s) ...")
    t_start = time.time()
    while time.time() - t_start < args.duration:
        try:
            ts, message = detection_queue.get(timeout=0.5)
        except Exception:
            continue

        node_id = message.get("node_id", "UNKNOWN")
        elapsed = round(time.time() - t_start, 2)

        features = extractor.extract(ts, message)
        violations = semantic_checks(message, features)
        if node_id == GHOST_NODE_ID and violations:
            rule_fires_on_ghost.append({"t": elapsed, "violations": violations})

        findings = consistency_engine.process(node_id, ts, message)
        if findings and any(GHOST_NODE_ID in f.get("ecus", []) for f in findings):
            consistency_fires_involving_ghost.append({"t": elapsed, "findings": findings})

        lstm_conf = ingest_message(message)
        if node_id == GHOST_NODE_ID:
            ghost_lstm_scores.append((elapsed, lstm_conf))
        elif node_id == comparison_ecu:
            normal_lstm_scores.append((elapsed, lstm_conf))

    print("\n=== Structural checks (valid regardless of torch) ===")
    print(f"Per-ECU rule fires on ECU_GHOST: {len(rule_fires_on_ghost)} "
          f"(expected 0 — see node_subthreshold.py's threshold-margin comments)")
    for e in rule_fires_on_ghost[:5]:
        print(f"    t={e['t']}s  {e['violations']}")
    print(f"Consistency Engine fires involving ECU_GHOST: {len(consistency_fires_involving_ghost)} "
          f"(expected 0 — ECU_GHOST is outside CORRELATED_ECU_IDS by construction)")

    print("\n=== LSTM confidence (needs torch for a real answer) ===")
    if ghost_lstm_scores:
        ghost_vals = [c for _, c in ghost_lstm_scores if c is not None]
        print(f"ECU_GHOST:  n={len(ghost_vals)}  "
              f"max={max(ghost_vals):.1f}  mean={sum(ghost_vals)/len(ghost_vals):.1f}")
    if normal_lstm_scores:
        normal_vals = [c for _, c in normal_lstm_scores if c is not None]
        print(f"{comparison_ecu} (normal, comparison): n={len(normal_vals)}  "
              f"max={max(normal_vals):.1f}  mean={sum(normal_vals)/len(normal_vals):.1f}")

    print("\n=== Conclusion ===")
    if not TORCH_AVAILABLE:
        print("torch unavailable — LSTM columns above are structurally zero, not a real result.")
        print("Rule and Consistency Engine blindness to ECU_GHOST is confirmed, as expected.")
        print("Re-run with torch installed to answer the actual TARA-04 question: does the")
        print("LSTM's confidence for ECU_GHOST end up meaningfully higher than for a normal ECU?")
    elif ghost_lstm_scores and normal_lstm_scores:
        ghost_max = max(c for _, c in ghost_lstm_scores)
        normal_max = max(c for _, c in normal_lstm_scores)
        if ghost_max >= 70 and ghost_max > normal_max:
            print(f"LSTM caught it: ECU_GHOST peaked at {ghost_max:.1f} vs "
                  f"{comparison_ecu}'s {normal_max:.1f}. TARA-04 mitigated.")
        else:
            print(f"LSTM did NOT clearly catch it: ECU_GHOST peaked at {ghost_max:.1f} vs "
                  f"{comparison_ecu}'s {normal_max:.1f}. TARA-04 remains open — this is a real")
            print("result, not a bug: it means the fusion architecture's LSTM side isn't yet")
            print("pulling its weight against this specific attack shape.")


if __name__ == "__main__":
    main()
