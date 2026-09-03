"""
Replay a recorded run through the ACTUAL detection pipeline (feature
extraction, physics rules, LSTM scoring, fusion, alert generation — the same
functions backend/main.py calls live) and score the result against the
recording's ground truth.

This is the piece that turns Evaluation.md from a skeleton into real
numbers: Detection Accuracy, False Positive Rate, Detection Delay, and
Rule-hits-vs-LSTM-hits, computed exactly as defined in Evaluation.md §2.

Usage (from project root):
    python scripts/evaluate_replay.py --run backend/recordings/run_001
    python scripts/evaluate_replay.py --run backend/recordings/run_001 --speed 0 --json-out report.json

Note on ground truth vs. dedup: backend/core/alerts.py's ACTIVE_ALERTS dedup
means only the *first* alert per node_id is ever generated for the life of
the process. That's exactly what "Detection Delay" wants (time to first
alert), so no special-casing is needed here — but it does mean re-running
this script imports a fresh alerts module each time to avoid stale state
leaking across runs (see `_fresh_alert_generator` below).
"""

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus import MessageBus
from backend.sim.replayer import TelemetryReplayer
from backend.core.features import FeatureExtractor
from backend.core.checks import semantic_checks
from backend.core.scoring import score_violations


def _fresh_alert_generator():
    """backend.core.alerts keeps a module-level ACTIVE_ALERTS dict, and
    backend.ai.advisor keeps a module-level LSTM singleton. Reimporting both
    fresh avoids state leaking in from a previous evaluation run within the
    same Python process."""
    for mod_name in ("backend.core.alerts", "backend.ai.advisor"):
        if mod_name in sys.modules:
            del sys.modules[mod_name]
    alerts_mod = importlib.import_module("backend.core.alerts")
    advisor_mod = importlib.import_module("backend.ai.advisor")
    return alerts_mod, advisor_mod


def load_ground_truth(run_dir: Path):
    gt_path = run_dir / "ground_truth.jsonl"
    with open(gt_path) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_pipeline(run_dir: Path, speed: float):
    alerts_mod, advisor_mod = _fresh_alert_generator()

    ground_truth = load_ground_truth(run_dir)
    telemetry_path = run_dir / "telemetry.jsonl"

    bus = MessageBus()
    detection_queue = bus.subscribe("vehicle_state")
    replayer = TelemetryReplayer(bus, telemetry_path, speed=speed)

    # Publish everything up front (bus fan-out means the queue just buffers
    # it) rather than interleaving publish/consume — simpler and avoids
    # timing races in the evaluation harness itself.
    published = replayer.run()

    extractor = FeatureExtractor()
    per_message_results = []  # aligned positionally with ground_truth

    processed = 0
    while processed < published:
        ts, message = detection_queue.get(timeout=5.0)
        node_id = message.get("node_id", "UNKNOWN")

        features = extractor.extract(ts, message)
        violations = semantic_checks(message, features)
        rule_severity, rule_conf = score_violations(violations)
        lstm_conf = advisor_mod.ingest_message(message)

        fused_conf = max(rule_conf, lstm_conf)
        alert_fired = bool(violations) or lstm_conf >= 70

        alert = None
        if alert_fired:
            fused_severity = rule_severity if rule_conf >= lstm_conf else (
                "critical" if lstm_conf >= 90
                else "high" if lstm_conf >= 75
                else "medium" if lstm_conf >= 60
                else "low"
            )
            alert = alerts_mod.generate_alert(
                node_id=node_id,
                violations=violations,
                severity=fused_severity,
                confidence=fused_conf,
                rule_conf=rule_conf,
                lstm_conf=lstm_conf,
            )

        per_message_results.append({
            "node_id": node_id,
            "rule_hit": bool(violations),
            "lstm_hit": lstm_conf >= 70,
            "alert_fired": alert_fired,
            "alert_is_first_for_node": alert is not None,
        })
        processed += 1

    return ground_truth, per_message_results


def compute_metrics(ground_truth, results):
    assert len(ground_truth) == len(results), (
        f"ground_truth ({len(ground_truth)}) and results ({len(results)}) "
        f"length mismatch — recording may be corrupt or replay was interrupted"
    )

    attack_total = attack_flagged = 0
    normal_total = normal_flagged = 0
    rule_only = lstm_only = both = 0

    first_attack_ts_by_node = {}
    first_alert_ts_by_node = {}

    for gt, res, ts_index in zip(ground_truth, results, range(len(results))):
        is_attack = gt["label"] == "attack"
        node_id = gt["node_id"]

        if is_attack:
            attack_total += 1
            first_attack_ts_by_node.setdefault(node_id, gt["timestamp"])
            if res["alert_fired"]:
                attack_flagged += 1
                if res["rule_hit"] and res["lstm_hit"]:
                    both += 1
                elif res["rule_hit"]:
                    rule_only += 1
                elif res["lstm_hit"]:
                    lstm_only += 1
                if res["alert_is_first_for_node"]:
                    first_alert_ts_by_node.setdefault(node_id, gt["timestamp"])
        else:
            normal_total += 1
            if res["alert_fired"]:
                normal_flagged += 1

    detection_delay_by_node = {
        node: round(first_alert_ts_by_node[node] - first_attack_ts_by_node[node], 3)
        for node in first_attack_ts_by_node
        if node in first_alert_ts_by_node
    }
    undetected_nodes = sorted(set(first_attack_ts_by_node) - set(first_alert_ts_by_node))

    return {
        "detection_accuracy": round(attack_flagged / attack_total, 4) if attack_total else None,
        "false_positive_rate": round(normal_flagged / normal_total, 4) if normal_total else None,
        "attack_messages_total": attack_total,
        "attack_messages_flagged": attack_flagged,
        "normal_messages_total": normal_total,
        "normal_messages_flagged": normal_flagged,
        "rule_hits_vs_lstm_hits": {"rule_only": rule_only, "lstm_only": lstm_only, "both": both},
        "detection_delay_seconds_by_node": detection_delay_by_node,
        "undetected_attack_nodes": undetected_nodes,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate detection pipeline against a recorded run")
    parser.add_argument("--run", required=True, help="Run directory (contains telemetry.jsonl + ground_truth.jsonl)")
    parser.add_argument("--speed", type=float, default=0, help="Replay speed multiplier, 0 = as fast as possible")
    parser.add_argument("--json-out", default=None, help="Optional path to write the full JSON report")
    args = parser.parse_args()

    run_dir = Path(args.run)
    t0 = time.time()
    ground_truth, results = run_pipeline(run_dir, speed=args.speed)
    metrics = compute_metrics(ground_truth, results)
    elapsed = round(time.time() - t0, 2)

    print(f"\n=== Evaluation: {run_dir} ({len(ground_truth)} messages, {elapsed}s wall time) ===")
    print(f"Detection Accuracy:    {metrics['detection_accuracy']}  "
          f"({metrics['attack_messages_flagged']}/{metrics['attack_messages_total']} attack messages flagged)")
    print(f"False Positive Rate:   {metrics['false_positive_rate']}  "
          f"({metrics['normal_messages_flagged']}/{metrics['normal_messages_total']} normal messages flagged)")
    print(f"Rule-only / LSTM-only / Both: {metrics['rule_hits_vs_lstm_hits']}")
    print(f"Detection delay by ECU (s): {metrics['detection_delay_seconds_by_node']}")
    if metrics["undetected_attack_nodes"]:
        print(f"UNDETECTED attack ECUs: {metrics['undetected_attack_nodes']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(metrics, indent=2))
        print(f"\nFull report written to {args.json_out}")


if __name__ == "__main__":
    main()
