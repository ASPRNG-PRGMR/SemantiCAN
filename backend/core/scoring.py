def score_violations(violations: list) -> tuple:
    """
    Returns (max_severity_label: str, confidence_score: float 0–100).

    Scoring:
      critical = 90 base
      high     = 72 base
      medium   = 55 base
      low      = 28 base
    Each additional violation stacks +8, capped at 100.
    This gives meaningful spread: one HIGH=72, two HIGH=80, HIGH+CRITICAL=98.
    """
    if not violations:
        return "low", 0.0

    severity_map = {
        "critical": 90,
        "high":     72,
        "medium":   55,
        "low":      28,
    }

    max_severity = max(
        violations, key=lambda v: severity_map.get(v["severity"], 0)
    )["severity"]

    base       = severity_map.get(max_severity, 50)
    confidence = min(100.0, base + 8.0 * (len(violations) - 1))

    return max_severity, confidence
