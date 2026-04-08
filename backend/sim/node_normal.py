import time
import random

ECU_IDS = [f"ECU_{i:03d}" for i in range(1, 121)]  # 120 ECUs


def start_normal_node(bus):
    """
    Normal ECU behaviour: publishes consistent, physically plausible vehicle data.
    Key fix: field is 'acceleration' (not 'accel') so checks.py can read it.
    """
    while True:
        for ecu_id in ECU_IDS:
            bus.publish(
                "vehicle_state",
                {
                    "node_id": ecu_id,
                    "velocity": random.uniform(40.0, 60.0),      # km/h
                    "acceleration": random.uniform(-1.0, 1.0),   # m/s²  ← fixed key
                    "steering_angle": random.uniform(-10.0, 10.0),
                    "power": random.uniform(10.0, 20.0),         # kW
                },
            )
        time.sleep(0.5)
