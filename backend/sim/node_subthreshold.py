"""
Sub-threshold / slow semantic drift attack — TARA-04.

Unlike node_stealth.py (which targets the Consistency Engine by exploiting
an unchecked field, brake_pressure), this attack is designed to test
whether the LSTM actually does the job the architecture claims it does:
catch a joint pattern that's individually plausible on every single
message, but statistically wrong across a sequence.

Design, matching TARA-04's definition exactly ("attacker with knowledge of
the fixed rule thresholds deliberately crafts values just inside the safe
boundary"):

  - velocity, acceleration, and steering_angle all stay well inside every
    rule threshold in backend/core/checks.py, with wide margin (see the
    comments below for the actual numbers against each rule).
  - Instead of node_normal.py's random-walk noise, this ECU publishes a
    perfectly smooth, deterministic sinusoidal pattern. Individually, each
    value looks like an ordinary cruise. As a *sequence*, it's nothing like
    what an LSTM trained on noisy random-walk telemetry learned as normal —
    that's the actual distributional drift TARA-04 describes.
  - Uses node_id "ECU_GHOST", which is NOT in the Consistency Engine's
    CORRELATED_ECU_IDS ({"ECU_SPEED","ECU_BRAKE","ECU_STEER"}), and
    publishes no brake_pressure field at all. This is deliberate: it
    isolates the test to the LSTM specifically. If the rules and the
    Consistency Engine both structurally cannot see this ECU, the only
    thing standing between this attack and going undetected is the LSTM.

Rule-threshold margins (see backend/core/checks.py for the actual rules):
  - velocity_without_acceleration needs velocity > 140 km/h; this stays
    within [40, 70] km/h — 2x margin from the threshold.
  - impossible_acceleration needs |accel| > 7 m/s²; peak here is ~0.87 m/s²
    — 8x margin.
  - unsafe_steering_angle needs velocity > 80 AND |steering| > 30; velocity
    never exceeds 70 here, so this can never fire regardless of steering.
  - acceleration_velocity_mismatch's guard requires |reported accel| > 2.0
    m/s² before it even evaluates; peak here is ~0.87 m/s² — the rule is
    structurally inert against this payload.
"""

import math
import time

GHOST_NODE_ID = "ECU_GHOST"

VELOCITY_CENTER_KMH = 55.0
VELOCITY_AMPLITUDE_KMH = 15.0     # oscillates between 40 and 70 km/h
VELOCITY_PERIOD_SECONDS = 30.0

STEERING_AMPLITUDE_DEG = 5.0
STEERING_PERIOD_SECONDS = 13.0    # deliberately not a clean multiple of the
                                   # velocity period, so the two signals
                                   # aren't trivially in lockstep


def start_ghost_node(bus, publish_interval: float = 0.5):
    """Continuously injects the sub-threshold drift pattern. Runs
    indefinitely — caller controls lifetime by not joining the thread."""
    print("[*] Sub-threshold (TARA-04) ghost node active")
    t = 0.0
    prev_velocity = None
    while True:
        omega_v = 2 * math.pi / VELOCITY_PERIOD_SECONDS
        velocity = VELOCITY_CENTER_KMH + VELOCITY_AMPLITUDE_KMH * math.sin(omega_v * t)

        # Analytic derivative, not a finite difference off noisy state —
        # this is what keeps reported acceleration perfectly consistent
        # with the actual velocity trajectory, so
        # acceleration_velocity_mismatch has nothing to catch even in
        # principle, not just by getting lucky with rounding.
        dv_dt_kmh_per_s = VELOCITY_AMPLITUDE_KMH * omega_v * math.cos(omega_v * t)
        acceleration = dv_dt_kmh_per_s / 3.6  # km/h/s -> m/s²

        omega_s = 2 * math.pi / STEERING_PERIOD_SECONDS
        steering = STEERING_AMPLITUDE_DEG * math.sin(omega_s * t)

        bus.publish("vehicle_state", {
            "node_id": GHOST_NODE_ID,
            "velocity": round(velocity, 3),
            "acceleration": round(acceleration, 4),
            "steering_angle": round(steering, 3),
        })

        t += publish_interval
        time.sleep(publish_interval)
