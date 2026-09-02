"""
Stealthy coordinated attack — designed to demonstrate the Consistency Engine
(backend/core/consistency.py, Phase3_Plan.md §3), not the existing per-ECU
rules.

Unlike node_attack.py's scenarios (deliberately blatant — huge velocity,
impossible acceleration), every message published here is individually
crafted to pass all four existing checks in backend/core/checks.py:

  - velocity stays well under 140 km/h
  - |acceleration| stays well under 7 m/s²
  - steering_angle stays well under 30 degrees
  - velocity is held constant across cycles, so derived (Δv/Δt) acceleration
    stays near zero and never mismatches the (also near-zero) reported value

The only anomaly is that ECU_BRAKE reports sustained high brake_pressure
(0.92) while ECU_SPEED reports flat velocity for the same window — a real
vehicle cannot do that. No existing rule reads brake_pressure at all, so
this passes every per-ECU check untouched; only a check that reasons
jointly across ECU_BRAKE and ECU_SPEED can catch it.
"""

import time

STEALTH_VELOCITY_KMH = 95.0     # constant — well under the 140 km/h rule threshold
STEALTH_ACCEL = 0.05            # near-zero — well under the 7 m/s² rule threshold
STEALTH_STEERING_DEG = 2.0      # well under the 30 degree rule threshold
STEALTH_BRAKE_PRESSURE = 0.92   # high — but never checked by any per-ECU rule


def _speed_payload():
    return {
        "velocity": STEALTH_VELOCITY_KMH,
        "acceleration": STEALTH_ACCEL,
        "steering_angle": STEALTH_STEERING_DEG,
    }


def _brake_payload():
    return {
        "brake_pressure": STEALTH_BRAKE_PRESSURE,
        "velocity": STEALTH_VELOCITY_KMH,
        "acceleration": STEALTH_ACCEL,
        "steering_angle": 0.0,
    }


def _steer_payload():
    return {
        "steering_angle": STEALTH_STEERING_DEG,
        "velocity": STEALTH_VELOCITY_KMH,
        "acceleration": STEALTH_ACCEL,
    }


def start_stealth_node(bus, publish_interval: float = 0.5):
    """Continuously injects a coordinated, per-rule-compliant attack across
    ECU_SPEED, ECU_BRAKE, and ECU_STEER. Runs indefinitely — caller controls
    lifetime by not joining the thread (mirrors node_attack.py)."""
    print("[*] Stealth (cross-ECU) attack node active")
    while True:
        bus.publish("vehicle_state", {"node_id": "ECU_SPEED", **_speed_payload()})
        bus.publish("vehicle_state", {"node_id": "ECU_BRAKE", **_brake_payload()})
        bus.publish("vehicle_state", {"node_id": "ECU_STEER", **_steer_payload()})
        time.sleep(publish_interval)
