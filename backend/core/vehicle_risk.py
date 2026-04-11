from backend.core.ecu_registry import get_ecu_weight


def compute_vehicle_risk(active_alerts: list) -> float:
    """
    Weighted vehicle-wide risk score (0–100).
    Safety-critical ECUs (brake, engine, steering) contribute more
    than low-criticality ECUs (infotainment, body).
    """
    if not active_alerts:
        return 0.0

    weighted_sum = 0.0
    max_possible = 0.0

    for alert in active_alerts:
        ecu    = alert["node_id"]
        weight = get_ecu_weight(ecu)
        weighted_sum += weight * (alert["confidence"] / 100.0)
        max_possible += weight

    if max_possible == 0:
        return 0.0

    return round(min((weighted_sum / max_possible) * 100.0, 100.0), 1)
