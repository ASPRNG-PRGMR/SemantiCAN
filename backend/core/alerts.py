import uuid
from datetime import datetime

from backend.core.vehicle_risk import compute_vehicle_risk

ACTIVE_ALERTS: dict = {}


def generate_alert(node_id: str, violations: list, severity: str, confidence: float):
    """
    Creates a new alert for node_id.
    Deduplicates — only one active alert per ECU at a time.
    Attaches AI advisory analysis.
    """
    # Deduplicate per ECU
    if node_id in ACTIVE_ALERTS:
        return None

    alert = {
        "alert_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "node_id": node_id,
        "violations": violations,
        "severity": severity,
        "confidence": confidence,
    }

    ACTIVE_ALERTS[node_id] = alert

    # AI advisory (imported here to avoid circular imports)
    try:
        from backend.ai.advisor import explain_vehicle_anomaly

        vehicle_summary = {
            "risk_score": compute_vehicle_risk(list(ACTIVE_ALERTS.values())),
            "active_ecus": len(ACTIVE_ALERTS),
            "anomalous_ecus": len(ACTIVE_ALERTS),
            "duration_seconds": 30,
            "anomalies": [
                {
                    "ecu": a["node_id"],
                    "violation": a["violations"],
                    "confidence": a["confidence"],
                }
                for a in ACTIVE_ALERTS.values()
            ],
        }

        alert["ai_analysis"] = explain_vehicle_anomaly(vehicle_summary)
    except Exception as exc:
        alert["ai_analysis"] = f"[AI advisory unavailable: {exc}]"

    return alert


def get_active_alerts() -> list:
    return list(ACTIVE_ALERTS.values())
