ECU_IDS = [f"ECU_{i:03d}" for i in range(1, 121)]   # 120 normal ECUs

MALICIOUS_ECUS = {
    "ECU_005": "speed_accel_mismatch",
    "ECU_042": "power_draw_spike",
    "ECU_099": "telemetry_freeze",
}
