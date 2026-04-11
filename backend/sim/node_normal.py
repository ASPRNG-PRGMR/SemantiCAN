import time
import random

ECU_IDS = [f"ECU_{i:03d}" for i in range(1, 121)]

# Physics limits
V_MIN, V_MAX   = 30.0,  80.0    # km/h  — cruise range
A_MAX          =  1.0           # m/s²  — max gentle accel step per cycle
STEER_MAX      = 10.0           # degrees — normal gentle steering


def start_normal_node(bus):
    """
    Publishes physically continuous vehicle telemetry for 120 ECUs.

    Each ECU has its own persistent velocity state that evolves smoothly
    each cycle (small random delta), so derived Δv/Δt stays within ±1 m/s².
    This prevents the acceleration_velocity_mismatch rule from firing on
    normal ECUs due to random velocity jumps.
    """
    # Initialise each ECU with a random starting velocity
    state = {ecu_id: random.uniform(40.0, 60.0) for ecu_id in ECU_IDS}
    dt = 0.5   # publish interval in seconds

    while True:
        for ecu_id in ECU_IDS:
            # Small velocity change this tick: ±(A_MAX * dt) km/h equivalent
            # Keep consistent: accel in m/s², velocity in km/h
            # 1 m/s² for 0.5 s = 0.5 m/s = 1.8 km/h change per cycle max
            accel  = random.uniform(-A_MAX, A_MAX)         # m/s²
            dv_kmh = accel * dt * 3.6                      # convert to km/h
            v_new  = state[ecu_id] + dv_kmh
            v_new  = max(V_MIN, min(V_MAX, v_new))         # clamp to cruise range
            state[ecu_id] = v_new

            bus.publish(
                "vehicle_state",
                {
                    "node_id":        ecu_id,
                    "velocity":       round(v_new, 2),
                    "acceleration":   round(accel, 3),
                    "steering_angle": round(random.uniform(-STEER_MAX, STEER_MAX), 2),
                    "power":          round(random.uniform(10.0, 20.0), 2),
                },
            )
        time.sleep(dt)
