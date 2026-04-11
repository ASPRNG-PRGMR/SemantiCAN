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
) -> dict | None:
    """
    Creates a new alert for node_id.
    Returns None if an alert for this ECU is already active (deduplication).
    Attaches a locally-generated SOC advisory string.
    """
    if node_id in ACTIVE_ALERTS:
        return None

    alert = {
        "alert_id":  str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "node_id":   node_id,
        "violations": violations,
        "severity":   severity,
        "confidence": confidence,
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
