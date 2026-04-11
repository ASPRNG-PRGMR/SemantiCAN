def velocity_matches_acceleration(expected_accel: float, derived_accel: float, tolerance: float = 1.5) -> bool:
    return abs(expected_accel - derived_accel) <= tolerance


def yaw_rate_limit(yaw_rate: float, max_rate: float = 2.5) -> bool:
    return abs(yaw_rate) <= max_rate
