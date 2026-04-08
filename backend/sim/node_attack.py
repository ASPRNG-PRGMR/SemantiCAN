import time
import random

ATTACK_ECUS = [
    {
        "node_id": "ECU_SPEED",
        "payload": lambda: {
            "velocity": 180.0,
            "acceleration": -12.0,   # impossible deceleration
            "steering_angle": 2.0,
        },
    },
    {
        "node_id": "ECU_BRAKE",
        "payload": lambda: {
            "brake_pressure": 0.95,
            "velocity": 120.0,
            "acceleration": 0.0,
            "steering_angle": 0.0,
        },
    },
    {
        "node_id": "ECU_STEER",
        "payload": lambda: {
            "steering_angle": 45.0,   # unsafe angle at speed
            "velocity": 80.0,
            "acceleration": 0.3,
        },
    },
]


def start_attack_node(bus):
    """
    Injects semantically anomalous ECU messages.
    Fix: publish plain dict — bus.publish() handles timestamp wrapping.
    """
    print("[*] Semantic attack node active")

    while True:
        for ecu in ATTACK_ECUS:
            message = {
                "node_id": ecu["node_id"],
                **ecu["payload"](),
            }
            bus.publish("vehicle_state", message)  # ← fixed: no (ts, message) wrapping

        time.sleep(2)
