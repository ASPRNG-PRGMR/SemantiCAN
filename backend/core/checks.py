def semantic_checks(message: dict, features: dict) -> list:
    """
    Physics-based semantic validation rules.
    Returns a list of violation dicts: {type, severity}.

    Unit conventions:
      velocity        — km/h  (as published by ECU nodes)
      acceleration    — m/s²  (as published by ECU nodes)
      derived_accel   — m/s²  (computed from Δvelocity_km_h / Δt, then /3.6)
    """
    violations = []

    velocity        = message.get("velocity",       0)
    acceleration    = message.get("acceleration",   0)
    steering_angle  = message.get("steering_angle", 0)
    # derived_acceleration is stored in km/h per second by FeatureExtractor;
    # convert to m/s² for comparison: ÷ 3.6
    derived_accel_raw = features.get("derived_acceleration", 0)
    derived_accel     = derived_accel_raw / 3.6

    # 1. Velocity jump without corresponding reported acceleration → HIGH
    #    Only flag if velocity is very high AND reported accel is near zero
    if velocity > 140 and abs(acceleration) < 1:
        violations.append({
            "type":     "velocity_without_acceleration",
            "severity": "high",
        })

    # 2. Physically impossible acceleration → CRITICAL
    #    Normal road vehicles cannot exceed ~7 m/s² in any direction
    if abs(acceleration) > 7:
        violations.append({
            "type":     "impossible_acceleration",
            "severity": "critical",
        })

    # 3. Unsafe steering angle at high speed → MEDIUM
    if velocity > 80 and abs(steering_angle) > 30:
        violations.append({
            "type":     "unsafe_steering_angle",
            "severity": "medium",
        })

    # 4. Reported acceleration vs derived acceleration mismatch → HIGH
    #    Only apply if:
    #    - We have a meaningful derived value (not first message, not near-zero dt)
    #    - Reported accel is significant (ignore tiny values)
    #    - Mismatch exceeds 4 m/s² (generous tolerance for simulator noise)
    if (
        abs(derived_accel_raw) > 0        # we actually have a derived value
        and abs(acceleration) > 2.0       # reported accel is non-trivial
        and abs(acceleration - derived_accel) > 4.0
    ):
        violations.append({
            "type":     "acceleration_velocity_mismatch",
            "severity": "high",
        })

    return violations
