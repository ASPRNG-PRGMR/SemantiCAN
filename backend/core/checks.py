def semantic_checks(message, features):
    """
    Returns a list of semantic violations with explicit severity.

    Uses both raw message fields and derived features from FeatureExtractor.
    """
    violations = []

    velocity = message.get("velocity", 0)
    acceleration = message.get("acceleration", 0)
    steering_angle = message.get("steering_angle", 0)
    derived_accel = features.get("derived_acceleration", 0)

    # 1. Velocity jump without reported acceleration → HIGH
    if velocity > 140 and abs(acceleration) < 1:
        violations.append({
            "type": "velocity_without_acceleration",
            "severity": "high",
        })

    # 2. Physically impossible acceleration → CRITICAL
    if abs(acceleration) > 7:
        violations.append({
            "type": "impossible_acceleration",
            "severity": "critical",
        })

    # 3. Unsafe steering at speed → MEDIUM
    if velocity > 80 and abs(steering_angle) > 30:
        violations.append({
            "type": "unsafe_steering_angle",
            "severity": "medium",
        })

    # 4. Reported acceleration vs derived acceleration mismatch → HIGH
    #    (catches spoofed telemetry that adjusts reported value but not physics)
    if abs(acceleration) > 0.5 and abs(acceleration - derived_accel) > 2.0:
        violations.append({
            "type": "acceleration_velocity_mismatch",
            "severity": "high",
        })

    return violations
