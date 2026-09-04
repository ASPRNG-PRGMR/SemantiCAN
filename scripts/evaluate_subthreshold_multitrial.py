"""
Multi-trial version of scripts/evaluate_subthreshold.py.

The single-run version answered "did the LSTM react at all" — yes, with
real separation (ghost mean 34.8 vs one normal ECU's mean 6.3 on the first
run). But a single trial against a single comparison ECU can't tell you:

  1. Is that separation typical, or did we get a lucky/unlucky draw?
  2. What's the actual false-positive rate — how often does a genuinely
     normal ECU spike past the 70 alert threshold on its own, across many
     ECUs, not just the one we happened to compare against?
  3. How often does ECU_GHOST reliably cross the alert threshold at least
     once per trial — since backend/core/alerts.py dedups per-node forever,
     one crossing is enough to produce a standing alert live, so the
     question that matters isn't "what's the mean confidence" but "what
     fraction of trials produce at least one alert-worthy reading."

Runs N independent trials, each with a FRESH LSTM (re-imports
backend.ai.advisor per trial so training state doesn't leak across runs),
and scores ECU_GHOST against a spread of COMPARISON_ECU_COUNT normal ECUs
per trial rather than just one.

Usage (from project root, needs torch):
    python scripts/evaluate_subthreshold_multitrial.py --trials 5 --duration 25
"""

import argparse
import importlib
import sys
import time
from pathlib import Path
from statistics import mean, stdev
from threading import Thread

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus import MessageBus
from backend.sim.node_normal import start_normal_node
from backend.sim.node_subthreshold import start_ghost_node, GHOST_NODE_ID

ALERT_THRESHOLD = 70  # matches backend/main.py's lstm_conf >= 70 trigger
COMPARISON_ECU_COUNT = 10


def _fresh_advisor_module():
    """Re-import backend.ai.advisor so each trial starts with an untrained
    model — otherwise the module-level singleton (_advisor) would carry
    training state and score history across trials."""
    for mod_name in ("backend.ai.advisor",):
        if mod_name in sys.modules:
            del sys.modules[mod_name]
    return importlib.import_module("backend.ai.advisor")


def run_trial(trial_idx: int, duration: float, ghost_delay: float, comparison_ecus: list):
    advisor_mod = _fresh_advisor_module()

    bus = MessageBus()
    detection_queue = bus.subscribe("vehicle_state")

    Thread(target=start_normal_node, args=(bus,), daemon=True).start()

    def _delayed_ghost():
        time.sleep(ghost_delay)
        start_ghost_node(bus)

    Thread(target=_delayed_ghost, daemon=True).start()

    ghost_scores = []
    normal_scores = {ecu: [] for ecu in comparison_ecus}

    t_start = time.time()
    while time.time() - t_start < duration:
        try:
            _, message = detection_queue.get(timeout=0.5)
        except Exception:
            continue

        node_id = message.get("node_id", "UNKNOWN")
        conf = advisor_mod.ingest_message(message)

        if node_id == GHOST_NODE_ID:
            ghost_scores.append(conf)
        elif node_id in normal_scores:
            normal_scores[node_id].append(conf)

    return {
        "torch_available": advisor_mod._TORCH_AVAILABLE,
        "ghost_scores": ghost_scores,
        "normal_scores": normal_scores,
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-trial TARA-04 sub-threshold evaluation")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--duration", type=float, default=25.0, help="Seconds per trial")
    parser.add_argument("--ghost-delay", type=float, default=5.0)
    args = parser.parse_args()

    comparison_ecus = [f"ECU_{i:03d}" for i in range(1, 121, 120 // COMPARISON_ECU_COUNT)][:COMPARISON_ECU_COUNT]

    print(f"[*] Running {args.trials} trials, {args.duration}s each, "
          f"comparing ECU_GHOST against {len(comparison_ecus)} normal ECUs per trial")
    print(f"    Comparison set: {comparison_ecus}\n")

    trial_results = []
    for i in range(args.trials):
        print(f"--- Trial {i+1}/{args.trials} ---")
        result = run_trial(i, args.duration, args.ghost_delay, comparison_ecus)
        if not result["torch_available"]:
            print("[!] torch not installed — aborting. This script only produces a real")
            print("    result with torch available (see evaluate_subthreshold.py for why).")
            return
        ghost_max = max(result["ghost_scores"]) if result["ghost_scores"] else 0.0
        ghost_mean = mean(result["ghost_scores"]) if result["ghost_scores"] else 0.0
        print(f"    ECU_GHOST: n={len(result['ghost_scores'])} max={ghost_max:.1f} mean={ghost_mean:.1f}")
        trial_results.append(result)

    # ── Aggregate across trials ──────────────────────────────────────────
    ghost_maxes  = [max(r["ghost_scores"]) if r["ghost_scores"] else 0.0 for r in trial_results]
    ghost_means  = [mean(r["ghost_scores"]) if r["ghost_scores"] else 0.0 for r in trial_results]
    ghost_alert_trials = sum(1 for m in ghost_maxes if m >= ALERT_THRESHOLD)

    # False-positive unit = (comparison ECU, trial) pair: did this normal
    # ECU cross the alert threshold at least once in this trial? This
    # matches how alerts.py actually behaves (dedup-per-node-forever), so
    # it's the right question to ask, not "what fraction of messages".
    normal_pairs_total = 0
    normal_pairs_alerted = 0
    all_normal_maxes = []
    for r in trial_results:
        for ecu, scores in r["normal_scores"].items():
            normal_pairs_total += 1
            m = max(scores) if scores else 0.0
            all_normal_maxes.append(m)
            if m >= ALERT_THRESHOLD:
                normal_pairs_alerted += 1

    print("\n=== Aggregate results across all trials ===")
    print(f"ECU_GHOST max confidence per trial: {[round(m,1) for m in ghost_maxes]}")
    print(f"ECU_GHOST mean confidence per trial: {[round(m,1) for m in ghost_means]}")
    if len(ghost_maxes) > 1:
        print(f"  -> max: mean={mean(ghost_maxes):.1f} stdev={stdev(ghost_maxes):.1f}")
        print(f"  -> mean: mean={mean(ghost_means):.1f} stdev={stdev(ghost_means):.1f}")
    print(f"ECU_GHOST crossed alert threshold ({ALERT_THRESHOLD}) in "
          f"{ghost_alert_trials}/{len(trial_results)} trials "
          f"({100*ghost_alert_trials/len(trial_results):.0f}%)")

    print(f"\nNormal-ECU false-alert rate: {normal_pairs_alerted}/{normal_pairs_total} "
          f"(ECU, trial) pairs crossed {ALERT_THRESHOLD} "
          f"({100*normal_pairs_alerted/normal_pairs_total:.1f}%)")
    if all_normal_maxes:
        print(f"  Normal ECU max-confidence distribution: "
              f"mean={mean(all_normal_maxes):.1f}, max observed={max(all_normal_maxes):.1f}")

    print("\n=== Conclusion ===")
    ghost_detection_rate = ghost_alert_trials / len(trial_results)
    normal_fp_rate = normal_pairs_alerted / normal_pairs_total
    if ghost_detection_rate >= 0.8 and normal_fp_rate <= 0.1:
        print(f"TARA-04: mitigated with reasonable confidence. ECU_GHOST alerted in "
              f"{100*ghost_detection_rate:.0f}% of trials against a "
              f"{100*normal_fp_rate:.1f}% false-alert rate on normal ECUs.")
    elif ghost_detection_rate > normal_fp_rate:
        print(f"TARA-04: partial evidence of mitigation. ECU_GHOST alert rate "
              f"({100*ghost_detection_rate:.0f}%) exceeds the normal-ECU false-alert rate "
              f"({100*normal_fp_rate:.1f}%), but not by enough margin/trials to call this")
        print("settled. Treat as a real signal worth tracking, not a closed TARA entry.")
    else:
        print(f"TARA-04: NOT clearly mitigated. ECU_GHOST alert rate "
              f"({100*ghost_detection_rate:.0f}%) does not clearly exceed the normal-ECU "
              f"false-alert rate ({100*normal_fp_rate:.1f}%) across {len(trial_results)} trials.")


if __name__ == "__main__":
    main()
