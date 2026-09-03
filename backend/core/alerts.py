"""
Alert generation with per-ECU deduplication.
The AI advisory is now handled by the local LSTM advisor (no external API).
"""

import uuid
from datetime import datetime

from backend.core.vehicle_risk import compute_vehicle_risk

ACTIVE_ALERTS: dict = {}


def generate_alert(
    node_id: str,
    violations: list,
    severity: str,
    confidence: float,
    rule_conf: float = 0.0,
    lstm_conf: float = 0.0,
) -> dict | None:
    """
    Creates a new alert for node_id.
    Returns None if an alert for this ECU is already active (deduplication).
    Attaches a locally-generated SOC advisory string.

    rule_conf / lstm_conf are the two detector-specific confidence scores
    that fed into the fused `confidence` value (see backend/main.py). They're
    used purely to attribute which detector(s) caught this alert — mirrors
    the same rule/lstm attribution scripts/evaluate_replay.py computes for
    Evaluation.md, but live rather than from a recording.
    """
    if node_id in ACTIVE_ALERTS:
        return None

    rule_hit = bool(violations)
    lstm_hit = lstm_conf >= 70
    if rule_hit and lstm_hit:
        detector = "both"
    elif rule_hit:
        detector = "rule"
    elif lstm_hit:
        detector = "lstm"
    else:
        detector = "unknown"

    alert = {
        "alert_id":  str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "node_id":   node_id,
        "violations": violations,
        "severity":   severity,
        "confidence": confidence,
        "detector":   detector,
    }

    ACTIVE_ALERTS[node_id] = alert

    # Build vehicle summary for advisory
    vehicle_summary = {
        "risk_score":    compute_vehicle_risk(list(ACTIVE_ALERTS.values())),
        "active_ecus":   len(ACTIVE_ALERTS),
        "anomalous_ecus": len(ACTIVE_ALERTS),
        "duration_seconds": 30,
        "anomalies": [
            {
                "ecu":        a["node_id"],
                "violation":  a["violations"],
                "confidence": a["confidence"],
            }
            for a in ACTIVE_ALERTS.values()
        ],
    }

    try:
        from backend.ai.advisor import explain_vehicle_anomaly
        alert["ai_analysis"] = explain_vehicle_anomaly(vehicle_summary)
    except Exception as exc:
        alert["ai_analysis"] = f"[Advisory unavailable: {exc}]"

    return alert


def get_active_alerts() -> list:
    return list(ACTIVE_ALERTS.values())


def get_detector_breakdown() -> dict:
    """Counts of currently-active alerts by which detector(s) caught them.
    Powers the dashboard's Detection Method donut chart."""
    counts = {"rule": 0, "lstm": 0, "both": 0, "unknown": 0}
    for alert in ACTIVE_ALERTS.values():
        key = alert.get("detector", "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts
