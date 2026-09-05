"""
Static reference data for the console's Detection and Evaluation tabs.

Everything here mirrors a document or a source file that already exists in
the repository. Nothing in this module is a new claim:

  RULES              backend/core/checks.py, mapped per docs/Detection.md 2.1
  CONSISTENCY_CHECKS backend/core/consistency.py, per docs/Detection.md 8.2
  COVERAGE_GAPS      docs/Detection.md 2.1 and 8.2 gap tables, docs/TARA.md 3
  EVALUATION         docs/Evaluation.md 4, regenerated from the scripts

Because it is a copy, it can drift. The rule thresholds below are the ones
`checks.py` and `consistency.py` actually apply, not the ones the prose
describes -- `Detection.md` said the acceleration mismatch rule fires at
2 m/s2 while `checks.py` has always used 4.0, and the doc has been corrected
to match the code. When a threshold moves, it moves in three places: the
check, this table, and the doc.

The evaluation figures are a recorded result, not a live measurement, so
every one of them is stamped with the script and the run that produced it.
A dashboard number with no provenance is indistinguishable from a number
somebody typed in.
"""

# ── Physics rules (backend/core/checks.py) ───────────────────────────────
# `threat` and `goal` come from docs/Detection.md 2.1, which in turn
# references the TARA entries in docs/TARA.md.

RULES = [
    {
        "rule":     "velocity_without_acceleration",
        "trigger":  "velocity > 140 km/h while |acceleration| < 1 m/s²",
        "severity": "high",
        "protects": "Vehicle telemetry integrity",
        "threat":   ["TARA-01"],
        "goal":     "Maintain telemetry integrity",
    },
    {
        "rule":     "impossible_acceleration",
        "trigger":  "|acceleration| > 7 m/s²",
        "severity": "critical",
        "protects": "Vehicle telemetry integrity",
        "threat":   ["TARA-01", "TARA-02"],
        "goal":     "Maintain telemetry integrity",
    },
    {
        "rule":     "unsafe_steering_angle",
        "trigger":  "|steering| > 30° while velocity > 80 km/h",
        "severity": "medium",
        "protects": "Vehicle directional-control integrity",
        "threat":   ["TARA-03"],
        "goal":     "Prevent hazardous steering commands",
    },
    {
        "rule":     "acceleration_velocity_mismatch",
        "trigger":  "reported vs derived Δv/Δt differ by > 4 m/s², "
                    "when |reported| > 2 m/s²",
        "severity": "high",
        "protects": "Vehicle telemetry integrity",
        "threat":   ["TARA-01"],
        "goal":     "Maintain telemetry integrity",
    },
]

# ── Cross-ECU consistency (backend/core/consistency.py) ──────────────────
# All three map to TARA-05, which names the Consistency Engine as its
# mitigation. They reason jointly across ECU_SPEED / ECU_BRAKE / ECU_STEER,
# so findings are attributed to the vehicle rather than to one ECU.

CONSISTENCY_CHECKS = [
    {
        "rule":     "speed_brake_inconsistency",
        "trigger":  "brake_pressure > 0.7 sustained 2.0s with velocity not "
                    "dropping by at least 0.5 km/h (exempt below 5 km/h)",
        "severity": "high",
        "ecus":     "ECU_BRAKE + ECU_SPEED",
        "threat":   ["TARA-05"],
    },
    {
        "rule":     "steering_without_expected_effect",
        "trigger":  "|steering| > 30° sustained 2.0s above 80 km/h with "
                    "max |acceleration| < 0.3 m/s²",
        "severity": "medium",
        "ecus":     "ECU_STEER + ECU_SPEED",
        "threat":   ["TARA-05"],
    },
    {
        "rule":     "cross_ecu_timing_skew",
        "trigger":  "last-seen timestamps across the three correlated ECUs "
                    "differ by > 1.0s",
        "severity": "medium",
        "ecus":     "all three correlated ECUs",
        "threat":   ["TARA-05"],
    },
]

# ── What nothing currently catches ───────────────────────────────────────
# A coverage table is only honest if it also says what is missing. These are
# the open TARA entries from docs/TARA.md 3, in that document's own words.

COVERAGE_GAPS = [
    ("TARA-04", "Slow semantic drift (sub-threshold spoofing)",
     "Open. Rules and the Consistency Engine are structurally blind to it "
     "by design; the LSTM was measured against it below and did not "
     "separate it from normal traffic."),
    ("TARA-06", "Poisoned LSTM baseline",
     "Unmitigated. The model trusts whatever is on the bus during its first "
     "~300 samples."),
    ("TARA-07", "Unauthenticated backend API",
     "Unmitigated. Six Flask endpoints, no auth; assumes a trusted local "
     "network."),
    ("TARA-08", "Spoofed ECU identity",
     "Unmeasured. The node_id field is taken at face value."),
    ("TARA-09", "Replayed legitimate telemetry",
     "Planned, not built. Design in docs/Phase3_Plan.md §2."),
]

# ── Evaluation results (docs/Evaluation.md §4) ───────────────────────────
# Regenerated 2026-09-05 with torch 2.14.0 present, which is what the
# previous numbers in Evaluation.md were explicitly waiting on: every prior
# figure was produced in an environment where advisor.py returns 0.0 for
# every message, so the LSTM columns were structurally empty rather than
# measured.

EVAL_PROVENANCE = (
    "scripts/evaluate_replay.py against backend/recordings/run_torch_001 "
    "— 3,616 messages, 15s, attacks injected at t=5s. Run 2026-09-05 "
    "with torch 2.14.0."
)

EVAL_METRICS = [
    {
        "label":  "Detection accuracy",
        "value":  "100%",
        "detail": "16/16 attack messages flagged",
        "tone":   "good",
    },
    {
        "label":  "False positive rate",
        "value":  "0.11%",
        "detail": "4/3,600 normal messages flagged — all four from the "
                  "LSTM. The pre-torch run measured 0%.",
        "tone":   "warn",
    },
    {
        "label":  "Detection delay",
        "value":  "0.0s",
        "detail": "all three attack ECUs; the payloads cross a rule "
                  "threshold on their first message",
        "tone":   "good",
    },
    {
        "label":  "Rule / LSTM / both",
        "value":  "16 / 0 / 0",
        "detail": "every true positive came from the rule engine alone",
        "tone":   "warn",
    },
]

# The point of the evaluation is not the pass marks, it is these two.
EVAL_FINDINGS = [
    {
        "title": "The LSTM contributed nothing on the standard scenario, "
                 "and cost 4 false positives",
        "body":  "With torch active, rule-only 16, LSTM-only 0, both 0, and "
                 "the false positive rate moved from 0% to 0.11%. On this "
                 "scenario the second detector is a net negative. That is "
                 "not a reason to remove it — the attack payloads are "
                 "blatant enough that the rules were always going to win — "
                 "but it means the standard scenario cannot be used as "
                 "evidence that detector fusion earns its complexity.",
        "tone":  "warn",
    },
    {
        "title": "TARA-04 is still open, and now it is measured rather than "
                 "assumed",
        "body":  "scripts/evaluate_subthreshold.py ran the ECU_GHOST "
                 "sub-threshold attack for 60s with the LSTM trained. Rules "
                 "fired 0 times and the Consistency Engine 0 times, both by "
                 "construction. The LSTM scored ECU_GHOST at mean 53.2 / max "
                 "100.0 against a normal ECU's mean 48.1 / max 100.0 — "
                 "not a separation, and both saturate. The detector meant to "
                 "cover this gap does not currently cover it.",
        "tone":  "bad",
    },
    {
        "title": "Cross-ECU correlation closed the TARA-05 gap it was "
                 "built for",
        "body":  "scripts/evaluate_consistency.py: a coordinated attack "
                 "holding brake_pressure=0.92 with flat velocity produced 0 "
                 "fires from all four per-ECU rules — none of them read "
                 "brake_pressure at all — and 51 Consistency Engine "
                 "findings, the first 0.5s after the attack began, at "
                 "confidence 72. Two legitimate control scenarios produced 0 "
                 "false positives.",
        "tone":  "good",
    },
]
