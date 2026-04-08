from backend.core.ecu_registry import get_ecu_weight


def compute_vehicle_risk(active_alerts: list) -> float:
    """
    Computes a weighted vehicle-wide risk score (0–100).

    ECUs with higher criticality weights (e.g. brake, engine) contribute more
    to the overall score than low-criticality ECUs (e.g. infotainment).
    """
    if not active_alerts:
        return 0.0

    weighted_sum = 0.0
    max_possible = 0.0

    for alert in active_alerts:
        ecu = alert["node_id"]
        weight = get_ecu_weight(ecu)
        weighted_sum += weight * (alert["confidence"] / 100)
        max_possible += weight

    if max_possible == 0:
        return 0.0

    risk = (weighted_sum / max_possible) * 100
    return round(min(risk, 100.0), 1)
