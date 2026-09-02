"""
Consistency Engine — Cross-ECU Correlation (Phase3_Plan.md §3, closes TARA-05).

Every existing rule in checks.py evaluates ONE ECU's message in isolation.
This is a new, second-stage engine that looks jointly across ECU_SPEED,
ECU_BRAKE, and ECU_STEER — the three correlated ECUs describing a single
simulated vehicle — for combinations that are physically inconsistent even
though no individual value crosses any single-ECU threshold.

Concretely: checks.py never inspects `brake_pressure` at all — no existing
rule reads that field. An attacker who holds brake_pressure high while
keeping velocity/acceleration/steering individually "boring" (i.e. below
every per-ECU rule's threshold) currently passes every rule in the system
untouched. That's not a hypothetical gap; it's a direct reading of
checks.py. See scripts/evaluate_consistency.py for a demonstration.

Findings are attributed to the vehicle (or the ECU combination involved),
not to a single ECU, per Phase3_Plan.md §3.5 — callers should score and
alert on them as a vehicle-wide signal, not fold them into a single ECU's
existing alert.
"""

from collections import deque

CORRELATED_ECU_IDS = {"ECU_SPEED", "ECU_BRAKE", "ECU_STEER"}

HISTORY_WINDOW_SECONDS = 6.0

# Speed-Brake Consistency
BRAKE_HIGH_THRESHOLD = 0.7
BRAKE_SUSTAINED_WINDOW_SECONDS = 2.0
VELOCITY_DECREASE_EPS_KMH = 0.5  # velocity must drop at least this much to count as "braking took effect"
STOPPED_VELOCITY_FLOOR_KMH = 5.0  # below this, "flat velocity while braking" is normal (stopped, holding brake)

# Speed-Accel-Steering Consistency
STEER_HIGH_THRESHOLD_DEG = 30.0
STEER_SUSTAINED_WINDOW_SECONDS = 2.0
SPEED_FLOOR_FOR_STEER_CHECK_KMH = 80.0
MIN_LATERAL_EFFECT_ACCEL = 0.3  # m/s² — simplified stand-in for "the turn had *some* physical effect"

# Cross-ECU Timing Consistency
TIMING_SKEW_THRESHOLD_SECONDS = 1.0


class ConsistencyEngine:
    def __init__(self):
        self._history = {ecu_id: deque() for ecu_id in CORRELATED_ECU_IDS}

    def process(self, node_id: str, timestamp: float, message: dict) -> list:
        """Feed one message in. Returns a list of finding dicts
        ({"type", "severity", "ecus", "detail"}) — empty if nothing to
        report. Only messages from CORRELATED_ECU_IDS are tracked; anything
        else is a no-op."""
        if node_id not in CORRELATED_ECU_IDS:
            return []

        hist = self._history[node_id]
        hist.append((timestamp, message))
        while hist and timestamp - hist[0][0] > HISTORY_WINDOW_SECONDS:
            hist.popleft()

        findings = []
        findings += self._check_speed_brake(timestamp)
        findings += self._check_steering_effect(timestamp)
        findings += self._check_timing_skew(timestamp)
        return findings

    def _recent(self, ecu_id: str, now: float, window: float):
        return [(t, m) for t, m in self._history[ecu_id] if now - t <= window]

    def _check_speed_brake(self, now: float) -> list:
        recent_brake = self._recent("ECU_BRAKE", now, BRAKE_SUSTAINED_WINDOW_SECONDS)
        recent_speed = self._recent("ECU_SPEED", now, BRAKE_SUSTAINED_WINDOW_SECONDS)
        if len(recent_brake) < 2 or len(recent_speed) < 2:
            return []

        if not all(m.get("brake_pressure", 0.0) > BRAKE_HIGH_THRESHOLD for _, m in recent_brake):
            return []

        v_start = recent_speed[0][1].get("velocity", 0.0)
        v_end = recent_speed[-1][1].get("velocity", 0.0)
        delta = v_end - v_start

        # A vehicle that is already stopped (or nearly so) and holding the
        # brake — e.g. at a red light — legitimately has flat velocity while
        # brake_pressure is high. That's normal, not a violation. Only a
        # vehicle that was still moving at the start of the window and
        # failed to slow down is inconsistent.
        if v_start <= STOPPED_VELOCITY_FLOOR_KMH:
            return []

        if delta > -VELOCITY_DECREASE_EPS_KMH:
            return [{
                "type": "speed_brake_inconsistency",
                "severity": "high",
                "ecus": ["ECU_BRAKE", "ECU_SPEED"],
                "detail": (
                    f"brake_pressure > {BRAKE_HIGH_THRESHOLD} sustained for "
                    f"{BRAKE_SUSTAINED_WINDOW_SECONDS}s while velocity moved by "
                    f"{delta:+.2f} km/h from {v_start:.1f} km/h (expected a decrease)"
                ),
            }]
        return []

    def _check_steering_effect(self, now: float) -> list:
        recent_steer = self._recent("ECU_STEER", now, STEER_SUSTAINED_WINDOW_SECONDS)
        recent_speed = self._recent("ECU_SPEED", now, STEER_SUSTAINED_WINDOW_SECONDS)
        if len(recent_steer) < 2 or len(recent_speed) < 2:
            return []

        if not all(abs(m.get("steering_angle", 0.0)) > STEER_HIGH_THRESHOLD_DEG for _, m in recent_steer):
            return []

        avg_velocity = sum(m.get("velocity", 0.0) for _, m in recent_speed) / len(recent_speed)
        if avg_velocity < SPEED_FLOOR_FOR_STEER_CHECK_KMH:
            return []

        max_accel_magnitude = max(abs(m.get("acceleration", 0.0)) for _, m in recent_speed)
        if max_accel_magnitude < MIN_LATERAL_EFFECT_ACCEL:
            return [{
                "type": "steering_without_expected_effect",
                "severity": "medium",
                "ecus": ["ECU_STEER", "ECU_SPEED"],
                "detail": (
                    f"steering > {STEER_HIGH_THRESHOLD_DEG}deg sustained at "
                    f"{avg_velocity:.1f} km/h with no corresponding acceleration "
                    f"signature (max |accel|={max_accel_magnitude:.2f} m/s²)"
                ),
            }]
        return []

    def _check_timing_skew(self, now: float) -> list:
        last_ts = {}
        for ecu_id in CORRELATED_ECU_IDS:
            hist = self._history[ecu_id]
            if len(hist) < 3:
                return []
            last_ts[ecu_id] = hist[-1][0]

        values = list(last_ts.values())
        skew = max(values) - min(values)
        if skew > TIMING_SKEW_THRESHOLD_SECONDS:
            return [{
                "type": "cross_ecu_timing_skew",
                "severity": "medium",
                "ecus": sorted(CORRELATED_ECU_IDS),
                "detail": f"last-seen timestamps across correlated ECUs differ by {skew:.2f}s",
            }]
        return []
