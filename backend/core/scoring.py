def score_violations(violations):
    """
    Returns (max_severity_label, confidence_score 0-100).
    """
    if not violations:
        return "low", 0

    severity_map = {
        "critical": 90,
        "high": 75,
        "medium": 60,
        "low": 30,
    }

    max_severity = max(violations, key=lambda v: severity_map.get(v["severity"], 0))["severity"]
    base = severity_map.get(max_severity, 50)

    # Each additional violation adds 5 points, capped at 100
    confidence = min(100, base + 5 * (len(violations) - 1))

    return max_severity, confidence
