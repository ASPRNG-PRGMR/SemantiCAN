# TARA - Threat Analysis and Risk Assessment - SemantiCAN

**Status:** Draft v0.1 - formalizes the threats identified in `Threat_Model.md` into ISO 21434-style TARA entries. This is the roadmap's highest-priority addition (Phase 2 Step 2).

## 1. Purpose

`Threat_Model.md` describes assets, attack surface, actors, assumptions, security goals, and trust boundaries. This document takes each relevant threat from that analysis and formalizes it into a TARA entry: **Threat → Damage Scenario → Attack Path → Security Goal → Mitigation**. This is the format used to reason about automotive cybersecurity risk under ISO 21434.

Each entry is numbered (`TARA-01`, `TARA-02`, ...) so it can be referenced from `Detection.md`'s rule mapping table and from future work items.

## 2. TARA Entries

### TARA-01 - Spoofed Speed ECU

| Field | Value |
|---|---|
| **Threat** | Spoofed / compromised `ECU_SPEED` reports a velocity inconsistent with reported acceleration |
| **Damage Scenario** | Vehicle telemetry integrity is lost; a downstream system or operator relying on speed data could make an unsafe decision, or a real fault could be masked by attacker-controlled values |
| **Attack Path** | Attacker compromises or impersonates `ECU_SPEED` on the vehicle network and publishes a crafted payload (e.g., velocity=180 km/h, accel=−12 m/s²) |
| **Security Goal** | Maintain telemetry integrity (Security Goal 1, `Threat_Model.md` §6) |
| **Mitigation** | Rules: `impossible_acceleration`, `acceleration_velocity_mismatch` (see `Detection.md` §2) |
| **Residual Risk** | Rules catch this scenario immediately and with high confidence; residual risk is low for this specific payload shape, but the rules are threshold-based and could miss a more subtle spoof (see TARA-05) |

### TARA-02 - Spoofed Brake ECU

| Field | Value |
|---|---|
| **Threat** | Spoofed / compromised `ECU_BRAKE` reports a brake/velocity/acceleration combination that is physically inconsistent |
| **Damage Scenario** | False braking telemetry could mask an actual braking failure, or cause an operator/system to misjudge vehicle deceleration state |
| **Attack Path** | Attacker compromises or impersonates `ECU_BRAKE` and publishes a crafted payload (e.g., brake=0.95, velocity=160 km/h, accel=8.5 m/s²) |
| **Security Goal** | Maintain telemetry integrity |
| **Mitigation** | Rule: `impossible_acceleration`, reinforced by LSTM drift detection (dual detection - see `Architecture.md` §5) |
| **Residual Risk** | Lower than TARA-01, since this scenario is the one explicitly used to demonstrate the value of detector fusion - both methods must fail for this to go undetected |

### TARA-03 - Spoofed Steering ECU

| Field | Value |
|---|---|
| **Threat** | Spoofed / compromised `ECU_STEER` reports an unsafe steering angle for the current speed |
| **Damage Scenario** | Vehicle loses directional-control integrity signal; a hazardous steering command could go unflagged by non-semantic (protocol-level) monitoring |
| **Attack Path** | Attacker compromises or impersonates `ECU_STEER` and publishes a crafted payload (e.g., steering=55°, velocity=100 km/h) |
| **Security Goal** | Prevent hazardous steering commands from going unnoticed |
| **Mitigation** | Rule: `unsafe_steering_angle` |
| **Residual Risk** | Single-rule coverage only (no LSTM corroboration in the current scenario set) - see TARA-05 for the coverage gap this implies |

### TARA-04 - Slow Semantic Drift (Sub-Threshold Spoofing)

| Field | Value |
|---|---|
| **Threat** | An attacker crafts telemetry values that individually stay under every rule threshold, but that are jointly implausible relative to normal ECU behavior over time |
| **Damage Scenario** | Same as TARA-01/02/03, but undetected by the rules engine because no single threshold is crossed |
| **Attack Path** | Attacker with knowledge of the fixed rule thresholds (e.g., stays under 7 m/s², under 30° at speed) deliberately crafts values just inside the "safe" boundary |
| **Security Goal** | Resilience to single-vector evasion (Security Goal 3) |
| **Mitigation** | LSTM anomaly scoring - designed specifically to catch distributional drift that fixed thresholds miss |
| **Residual Risk** | Depends entirely on LSTM training quality and baseline cleanliness (see TARA-06). Not yet measured - this is exactly what `Evaluation.md` §2 (Detection Accuracy, Rule Hits vs. LSTM Hits) is meant to quantify |

### TARA-05 - Rule Threshold Blind Spots

| Field | Value |
|---|---|
| **Threat** | The four current rules cover a narrow, hand-picked set of physical impossibilities; ECUs or value combinations outside that set have no rule coverage at all |
| **Damage Scenario** | An anomaly type not anticipated by the current rule set (e.g., battery/BMS anomalies, timing anomalies) goes undetected unless the LSTM happens to catch it |
| **Attack Path** | Attacker targets a telemetry dimension or ECU not covered by any existing rule |
| **Security Goal** | Telemetry integrity monitoring (Security Goal 1) - currently only partially met |
| **Mitigation** | Implemented: Cross-ECU Correlation / Consistency Engine (`backend/core/consistency.py`), wired into the live detection loop in `backend/main.py`. Demonstrated in `scripts/evaluate_consistency.py`: a coordinated attack across `ECU_SPEED`/`ECU_BRAKE`/`ECU_STEER`, individually crafted to pass every existing per-ECU rule (sustained `brake_pressure=0.92` with flat velocity — a field no per-ECU rule ever reads), produces 0 detections from the existing rule set and is caught immediately by the Consistency Engine's Speed-Brake check. Verified against two legitimate scenarios (braking to a stop, holding the brake at a stoplight) with 0 false positives after an initial FP was found and fixed during testing (the check originally didn't account for a vehicle already stopped and holding the brake). |
| **Residual Risk** | Reduced from high to partial. The initial check set covers Speed-Brake and Speed-Steering-Acceleration consistency plus cross-ECU timing skew; it does not yet cover every possible cross-ECU combination, and thresholds (brake sustain window, velocity-decrease epsilon) are not yet tuned against anything beyond this simulation's simplified physics — see `Detection.md` §2.1 gap table and `Evaluation.md` for what's still open |

### TARA-06 - Poisoned LSTM Baseline

| Field | Value |
|---|---|
| **Threat** | An attacker present during the ~300-sample baseline collection window influences what the LSTM learns as "normal" |
| **Damage Scenario** | The model's definition of normal becomes attacker-shifted, silently raising the bar for what counts as anomalous - a slow-motion version of TARA-04 |
| **Attack Path** | Attacker (insider, supply-chain, or on-bus actor present at startup) injects subtly-biased-but-plausible telemetry during the training window, before the LSTM has anything to compare against |
| **Security Goal** | Detection pipeline integrity (Asset, `Threat_Model.md` §2) |
| **Mitigation** | None currently implemented. Candidate mitigations: baseline validation against the rule engine before training, anomaly-aware training-sample filtering, or periodic retraining with human-reviewed baselines |
| **Residual Risk** | High and currently unmitigated - flagged in `Threat_Model.md` §5 as an explicit assumption rather than a solved problem |

### TARA-07 - Unauthenticated Backend API

| Field | Value |
|---|---|
| **Threat** | Any network-adjacent client can query the six Flask API endpoints without authentication |
| **Damage Scenario** | Information disclosure of vehicle telemetry/alert state to an unauthorized party; in a networked (non-localhost) deployment, this could also inform an attacker about which of their attacks are already being detected |
| **Attack Path** | Attacker on the same network as the backend sends direct HTTP requests to the Flask API |
| **Security Goal** | N/A directly (this is an infrastructure gap rather than a telemetry-integrity gap), but it undermines Auditability and operator trust in the SOC Dashboard asset |
| **Mitigation** | None currently implemented - prototype assumes a trusted local network (`Threat_Model.md` §5) |
| **Residual Risk** | High in any deployment beyond localhost; low in the current single-machine simulation context. Explicitly out of scope for the detection-focused phases of this roadmap, but tracked in `Future_Work.md` §4 |

### TARA-08 - Spoofed ECU Identity

| Field | Value |
|---|---|
| **Threat** | The controller trusts the `ECU_ID` field at face value; an attacker could impersonate a legitimate, non-attack ECU rather than being confined to the three designated attack ECUs |
| **Damage Scenario** | Detection logic that reasons per-ECU (e.g., criticality weighting in the Vehicle Risk Engine) could be misapplied if the attacker's messages are attributed to the wrong ECU |
| **Attack Path** | Attacker sends telemetry claiming the identity of a normal ECU, rather than one of the pre-defined attack ECUs |
| **Security Goal** | ECU trustworthiness (Asset, `Threat_Model.md` §2) |
| **Mitigation** | None currently implemented - this prototype does not model message-origin authentication at all; the current attack scenarios use dedicated, honestly-labeled attack ECUs rather than testing this specific threat |
| **Residual Risk** | Unmeasured. This is explicitly flagged as an open question in `Threat_Model.md` §8 rather than assumed away |

### TARA-09 - Replayed Legitimate Telemetry

| Field | Value |
|---|---|
| **Threat** | An attacker records legitimate, previously valid telemetry messages and re-transmits them later, out of their original real-time context |
| **Damage Scenario** | The pipeline sees protocol-valid, physically-plausible content, since the values really were valid once, so neither the rule engine nor the LSTM has a content-based reason to flag it |
| **Attack Path** | Attacker captures a window of normal telemetry and replays it later, either to mask actual vehicle behavior or to create a false impression of normal operation during a real attack |
| **Security Goal** | Telemetry integrity monitoring, extended from value plausibility to time plausibility |
| **Mitigation** | Planned, not yet implemented. Full design in `Phase3_Plan.md` §2 (sequence and freshness checking, new `replay_detected` rule) |
| **Residual Risk** | High and currently unmitigated. This is the one TARA entry with an active implementation plan already written, see `Phase3_Plan.md` |

## 3. Summary Table

| ID | Threat | Security Goal | Mitigated? |
|---|---|---|---|
| TARA-01 | Spoofed Speed ECU | Telemetry integrity | Yes - rules |
| TARA-02 | Spoofed Brake ECU | Telemetry integrity | Yes - rules + LSTM |
| TARA-03 | Spoofed Steering ECU | Hazardous steering prevention | Yes - rules |
| TARA-04 | Slow semantic drift (sub-threshold) | Resilience to evasion | Partial - LSTM, unquantified |
| TARA-05 | Rule threshold blind spots | Telemetry integrity | Partial - Cross-ECU Correlation implemented, see `Detection.md` §8 |
| TARA-06 | Poisoned LSTM baseline | Detection pipeline integrity | No |
| TARA-07 | Unauthenticated backend API | Auditability / operator trust | No |
| TARA-08 | Spoofed ECU identity | ECU trustworthiness | No |
| TARA-09 | Replayed legitimate telemetry | Telemetry integrity (time plausibility) | Planned, see `Phase3_Plan.md` |

## 4. Next Steps

- Feed TARA-01 through TARA-03 into `Detection.md`'s Rule → Threat mapping table (replacing the current TBD placeholders) - done as part of this update.
- Quantify TARA-04's residual risk once `Evaluation.md` has real Rule Hits vs. LSTM Hits data.
- TARA-05 and TARA-09 now have a design-stage mitigation plan in `Phase3_Plan.md`. TARA-06, TARA-07, and TARA-08 remain unaddressed and are candidates for a future phase.
