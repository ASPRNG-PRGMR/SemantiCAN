import time

ATTACK_ECUS = [
    {
        "node_id": "ECU_SPEED",
        "payload": lambda: {
            "velocity":       180.0,   # impossible speed
            "acceleration":   -12.0,   # physically impossible deceleration
            "steering_angle":   2.0,
        },
    },
    {
        "node_id": "ECU_BRAKE",
        "payload": lambda: {
            "brake_pressure":  0.95,   # full brake applied
            "velocity":       160.0,   # but velocity keeps rising — impossible
            "acceleration":    8.5,    # > 7 m/s² threshold → CRITICAL
            "steering_angle":   0.0,
        },
    },
    {
        "node_id": "ECU_STEER",
        "payload": lambda: {
            "steering_angle": 55.0,    # extreme unsafe angle
            "velocity":      100.0,    # well above 80 km/h threshold
            "acceleration":    0.3,
        },
    },
]


def start_attack_node(bus):
    """Continuously injects semantically anomalous ECU messages."""
    print("[*] Semantic attack node active")
    while True:
        for ecu in ATTACK_ECUS:
            message = {"node_id": ecu["node_id"], **ecu["payload"]()}
            bus.publish("vehicle_state", message)
        time.sleep(2)
