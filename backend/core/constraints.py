def velocity_matches_acceleration(expected_accel, derived_accel, tolerance=1.5):
    return abs(expected_accel - derived_accel) <= tolerance


def yaw_rate_limit(yaw_rate, max_rate=2.5):
    return abs(yaw_rate) <= max_rate
