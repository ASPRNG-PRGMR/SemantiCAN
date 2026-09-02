# Phase 3 Implementation Plan - Attack Replay, Replay Attack Detection, Cross-ECU Correlation

**Status: PLANNED. Design only. No code has been written yet.** This document exists to fully specify these three features before implementation, so that when coding starts (in a session with the actual repository), the work is executing a reviewed plan rather than improvising. This document should be treated as the source of truth for scope, design, and interfaces until implementation begins, at which point it should be updated to reflect what was actually built and any deviations from this plan.

## 0. Why These Three, Together

The roadmap's Phase 3 instruction is to pick one or two technical improvements. Three were selected here because they are not independent: Attack Replay is infrastructure that Replay Attack Detection needs in order to be tested meaningfully, and both directly strengthen Evaluation.md, which is itself a separately prioritized roadmap item. Building Attack Replay first, then Replay Attack Detection, then Cross-ECU Correlation, is a natural dependency order rather than three unrelated features bolted together.

| Feature | Type | Depends on |
|---|---|---|
| Attack Replay | Evaluation and testing infrastructure | Nothing (build first) |
| Replay Attack Detection | New detection capability | Attack Replay (for test data and regression testing) |
| Cross-ECU Correlation | New detection capability | Nothing technically, but reuses Attack Replay for evaluation once built |

## 1. Feature A: Attack Replay Infrastructure

### 1.1 Goal

Allow a full telemetry run (normal traffic plus injected attacks) to be recorded to disk, then replayed through the detection pipeline later, either to reproduce a specific scenario for debugging, to regression test detection logic after a code change, or to generate the accuracy and delay numbers needed in Evaluation.md.

### 1.2 What Gets Recorded

Every message that crosses the Message Bus, in publish order, with:

- `timestamp` (simulation time, not wall clock, so replay speed is independent of recording speed)
- `ecu_id`
- raw payload fields (velocity, acceleration, steering angle, brake, and any future fields)
- a `ground_truth_label` field: `normal` or `attack`, plus which attack scenario if applicable. This is recording metadata only. It must never be passed into the detection pipeline itself, since the whole point of the evaluation is to check whether the pipeline can tell the difference without being told.

### 1.3 Storage Format

A newline-delimited JSON file (`.jsonl`), one message per line, under a new `backend/recordings/` directory. Newline-delimited JSON was chosen over a single JSON array because it can be streamed line by line during both recording and replay, without loading an entire run into memory, and because a partially-written recording (e.g., if a run is killed) is still readable up to the last complete line.

Example line:
```json
{"timestamp": 12.4, "ecu_id": "ECU_SPEED", "velocity": 180.0, "acceleration": -12.0, "ground_truth_label": "attack", "scenario": "spoofed_speed"}
```

### 1.4 New Components

| Component | File (proposed) | Responsibility |
|---|---|---|
| `TelemetryRecorder` | `backend/sim/recorder.py` | Subscribes to the Message Bus like any other consumer; writes every message plus ground-truth label to a `.jsonl` file as it happens |
| `TelemetryReplayer` | `backend/sim/replayer.py` | Reads a `.jsonl` file and republishes messages to the Message Bus, preserving original inter-message timing (or at a configurable speed multiplier), with `ground_truth_label` stripped before publishing |
| Recording manifest | `backend/recordings/<run_id>/manifest.json` | Records run metadata: start time, scenario config used, sim.yaml snapshot, so a recording is self-describing |

### 1.5 How This Plugs Into the Existing Architecture

The recorder attaches to the Message Bus exactly where the Semantic Integrity Controller already attaches, as a second subscriber. It does not sit in the detection path and cannot affect detection latency or behavior. The replayer, when active, replaces the Normal/Attack ECU Nodes as the publisher into the bus. From the Semantic Integrity Controller's point of view, a replayed run is indistinguishable from a live simulated run, which is the property that makes replay useful for regression testing: the same code path is exercised either way.

```
Live mode:   ECU Nodes -> Message Bus -> Controller -> ...
                              |
                              v
                        TelemetryRecorder -> recordings/*.jsonl

Replay mode: TelemetryReplayer -> Message Bus -> Controller -> ...
             (reads recordings/*.jsonl)
```

### 1.6 CLI / Usage (proposed)

```
python -m backend.sim.record --output recordings/run_2026_08_11.jsonl
python -m backend.sim.replay --input recordings/run_2026_08_11.jsonl --speed 1.0
python -m backend.sim.replay --input recordings/run_2026_08_11.jsonl --speed 10.0   # fast evaluation runs
```

### 1.7 Evaluation Use

Once a recording exists with ground-truth labels, an evaluation script can:

1. Replay the recording.
2. Capture every alert the pipeline generates, with timestamps.
3. Compare alert timestamps and affected ECUs against the ground-truth labels from the manifest.
4. Compute Detection Accuracy, False Positive Rate, and Detection Delay directly, which are currently listed as TBD in `Evaluation.md`.

This closes the loop between Attack Replay and the evaluation metrics without requiring a human to manually watch a live run and eyeball whether detection worked.

### 1.8 Open Design Questions

- Should ground-truth labels live in the recording file itself (simpler, but means the recording file must be handled carefully so it is never fed directly into a "live" code path) or in a separate sidecar file keyed by timestamp? Current lean is sidecar, to make it structurally impossible to leak ground truth into the detection pipeline by accident.
- Whether simulation time or wall-clock time should be the default replay clock. Current lean is simulation time by default, since detection delay should be measured in simulation time to be comparable across runs.

---

## 2. Feature B: Replay Attack Detection

### 2.1 Threat Basis

This corresponds to a new TARA entry, **TARA-09**, to be added to `TARA.md`:

| Field | Value |
|---|---|
| **Threat** | An attacker records legitimate, valid telemetry messages and re-transmits them later, out of their original real-time context |
| **Damage Scenario** | The detection pipeline sees protocol-valid, physically-plausible content (because it really was valid, once) and neither the rule engine nor the LSTM has any reason to flag it on content alone, since nothing about the values themselves is wrong |
| **Attack Path** | Attacker captures a window of normal telemetry (e.g., a "vehicle stationary" or "vehicle braking normally" window) and replays it later, either to mask what the vehicle is actually doing or to create a false impression of normal operation during an actual attack |
| **Security Goal** | Telemetry integrity monitoring, extended from "is this value physically plausible" to "is this value happening at a plausible time relative to what came before it" |
| **Mitigation** | Planned: sequence and freshness checking, described below |
| **Residual Risk** | Currently unmitigated (this document is the mitigation plan) |

This is meaningfully different from TARA-01 through TARA-04, all of which assume the attacker crafts new (possibly false) values. Replay attacks use only real values, which is exactly why the existing rule engine and LSTM, both of which reason about value plausibility, are not designed to catch them.

### 2.2 Detection Approach

Two complementary checks, mirroring the project's existing "rules plus learned model" philosophy:

**2.2.1 Sequence / Freshness Check (rule-based, deterministic)**

Every ECU message in a real (even simulated) system has an implicit or explicit ordering. The proposed check:

- Track, per `ecu_id`, the timestamp and a content hash of the last N messages seen (N configurable, default 50).
- Flag a message as a suspected replay if its content hash exactly matches a previously seen message from the same ECU, but its timestamp gap from that prior occurrence is inconsistent with the ECU's normal publish interval (i.e., it is not simply a legitimately repeated steady-state reading, like velocity holding constant at 0 while parked).
- The "inconsistent gap" threshold needs to be tuned against real steady-state behavior in the simulation to avoid flagging legitimately repeated values (this is the main false-positive risk for this feature and should be an explicit evaluation target once Attack Replay infrastructure exists).

**2.2.2 Sequence Number / Monotonicity Check (if ECUs are extended to emit one)**

If a per-ECU monotonic sequence number is added to the simulated message format (a reasonable, low-cost addition since this is a simulation the project controls), replay becomes trivially detectable: a repeated or out-of-order sequence number from a given ECU is unambiguous evidence of replay, with no threshold tuning required. This is flagged as the preferred long-term approach, with the content-hash approach above as a fallback that also generalizes to a real CAN bus where sequence numbers may not be under this project's control.

### 2.3 New Rule

| Rule | Trigger condition | Severity |
|---|---|---|
| `replay_detected` | Duplicate content hash from the same `ecu_id` with an implausible time gap, or (if sequence numbers are added) a non-monotonic or repeated sequence number | HIGH |

This is designed to sit alongside the four existing rules in `backend/core/checks.py`, using the same explainable, threshold-based philosophy described in `Detection.md` §1.

### 2.4 Data Structures Needed

- A per-ECU ring buffer or bounded deque of `(timestamp, content_hash, sequence_number_if_present)` tuples, sized by the freshness window (N=50 default), living inside the Semantic Integrity Controller alongside the existing feature extraction state.
- This is new state, not currently present in the controller, since the existing rules are stateless per-message checks. This is the main architectural change this feature introduces, and should be called out explicitly in `Architecture.md` once implemented.

### 2.5 Interaction With Existing Detectors

Replay detection is intentionally kept as its own rule rather than folded into the LSTM, because a replay attack produces in-distribution values by definition (they are real values), so the LSTM is structurally the wrong tool for this threat. This is a case where the roadmap's "rules catch explainable, deterministic violations" framing (`Detection.md` §1) fits better than the learned-model approach, and is worth stating explicitly in `Detection.md` once this rule is implemented, so the choice reads as deliberate rather than an oversight of "why isn't this in the LSTM."

### 2.6 Testing Plan

Once Attack Replay (Feature A) exists, testing this feature is direct: record a normal run, then use the Attack Replay tooling itself to intentionally re-inject a captured window mid-run, and confirm `replay_detected` fires. This is a case where Feature A is not just infrastructure for evaluation, it is also the attack-generation tool needed to test Feature B, which is part of why the two are sequenced together.

### 2.7 Open Design Questions

- Whether to add sequence numbers to the simulated ECU message format now (cleaner detection, but changes the message schema and needs a decision about whether that schema should model a real CAN frame's constraints) or rely purely on content-hash plus timing (schema-neutral, more realistic if this project ever ingests real CAN captures, but noisier).
- What counts as a "legitimately repeated" value needs a concrete definition per telemetry field before the false-positive rate can be evaluated (e.g., is velocity=0.0 for 30 consecutive samples while parked a replay or normal steady state? Almost certainly normal, but the rule needs to encode that explicitly rather than accidentally).

---

## 3. Feature C: Cross-ECU Correlation

### 3.1 Goal

Move from independent per-ECU rules (the current `velocity_without_acceleration`, `impossible_acceleration`, `unsafe_steering_angle`, `acceleration_velocity_mismatch`, each of which looks at a single ECU's own values) to a check that reasons jointly across speed, brake, and steering. This is explicitly called out in the roadmap as the change that would make SemantiCAN feel closest to a production system, since real vehicle security monitoring rarely evaluates one sensor in isolation.

### 3.2 New Component: Consistency Engine

A new stage in the pipeline, positioned alongside (not replacing) the existing per-ECU checks:

```
Vehicle
  |
  v
Message Bus
  |
  v
Semantic Integrity Controller
  |-- Per-ECU Physics Rules  (existing)
  |-- Per-ECU LSTM Scoring   (existing)
  |-- Consistency Engine     (new, cross-ECU)
  |
  v
Risk Engine
  |
  v
SOC Dashboard
```

This updates the security architecture diagram first introduced in `Architecture.md` §2 and `Phase 2 Step 4` of the roadmap, and should replace that diagram once implemented.

### 3.3 What the Consistency Engine Checks

The Consistency Engine needs a short time window of recent messages from multiple ECUs (not just one), which is itself an architectural change: current rules evaluate one message at a time from one ECU. Proposed initial checks:

| Check | Logic | Rationale |
|---|---|---|
| **Speed-Brake Consistency** | If brake pressure is high (e.g., > 0.7) and sustained for more than a short window, velocity should be decreasing; if velocity is flat or increasing while brake is high, flag it | A real vehicle cannot brake hard and maintain or gain speed |
| **Speed-Acceleration-Steering Consistency** | High-magnitude steering input at high speed should correlate with some lateral effect on the reported trajectory (even in this simulation's simplified physics, a large steering angle held at high sustained speed with zero corresponding change anywhere else is suspicious) | Complements the existing single-ECU `unsafe_steering_angle` rule by checking for a physically expected side effect, not just the steering value alone |
| **Cross-ECU Timing Consistency** | Speed, brake, and steering messages for the same vehicle should arrive at roughly consistent intervals relative to each other; a large skew (one ECU's timestamps drifting relative to the others) is itself worth flagging, independent of content | Catches a compromised ECU whose reporting cadence has been tampered with, even if individual values look plausible |

### 3.4 Data Structures Needed

- A small per-vehicle (in this simulation, effectively global, since it is one simulated vehicle) sliding window holding the most recent message from each of the three correlated ECUs (`ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER`), refreshed as new messages arrive.
- This window is read by the Consistency Engine on every incoming message from any of the three, meaning the Consistency Engine runs after the per-ECU checks, not instead of them.

### 3.5 Scoring and Fusion Impact

Currently, fusion is `max(rule_confidence, lstm_confidence)`, computed per-ECU. A cross-ECU finding does not belong to a single ECU, so this needs to be extended. Proposed approach: a Consistency Engine finding produces its own confidence score, attributed to the vehicle as a whole (or to the combination of ECUs involved) rather than to one ECU, and is fed into the Vehicle Risk Engine as an additional, explicitly cross-ECU risk factor, separate from (but summed or maxed alongside) the existing per-ECU risk contributions. This needs a small extension to `backend/core/vehicle_risk.py`, and should be documented as a change to the scoring model once implemented, since it is a departure from the purely per-ECU fusion described in `Detection.md` §4 today.

### 3.6 New TARA Coverage

This feature directly addresses **TARA-05** (Rule Threshold Blind Spots) from `TARA.md`, specifically the gap around anomalies that no single-ECU rule was designed to catch. Once implemented, TARA-05's "Mitigated?" status in the TARA summary table should move from "No - planned" to reference this feature.

### 3.7 Open Design Questions

- How large the cross-ECU time window should be (too small: legitimate slightly-skewed message timing across ECUs gets flagged; too large: real inconsistencies get smoothed over and missed).
- Whether Consistency Engine findings should be able to trigger an alert on their own, or only act as a confidence booster on top of an existing per-ECU signal. Current lean is that they should be able to trigger independently, since the entire motivation for this feature is catching things no single-ECU rule would catch in the first place.

---

## 4. Suggested Build Order

1. **Attack Replay infrastructure** (Feature A). No dependencies. Immediately useful for `Evaluation.md` even before the other two features exist, since it can evaluate the current four rules and the LSTM as-is.
2. **Replay Attack Detection** (Feature B). Uses Feature A both to generate test replay attacks and to regression test the new rule.
3. **Cross-ECU Correlation** (Feature C). Independent of A and B technically, but evaluating it properly benefits from A being in place first.

## 5. Status Tracking

| Feature | Design status | Code status | Docs updated |
|---|---|---|---|
| Attack Replay | Complete (this document) | **Implemented** (`backend/sim/recorder.py`, `replayer.py`, `record.py`, `replay.py`, `scripts/evaluate_replay.py`) | `Architecture.md` §4.7/§6, `Evaluation.md` §4 |
| Replay Attack Detection | Complete (this document) | Not started | — |
| Cross-ECU Correlation | Complete (this document) | **Implemented** (`backend/core/consistency.py`, wired into `backend/main.py`; demo/eval in `scripts/evaluate_consistency.py`, attack scenario in `backend/sim/node_stealth.py`) | `Architecture.md` §4.3.1/§2, `Detection.md` §8.2, `TARA.md` TARA-05 |

Notable deviation from plan: implementation surfaced one real bug not anticipated in this document — `backend/sim/bus.py`'s `MessageBus` gave every subscriber to a topic the same queue rather than fanning out independently, which Attack Replay's second-subscriber design would have silently broken detection on. Fixed as part of Feature A. Also, the Consistency Engine's first Speed-Brake check implementation false-positived on a vehicle stopped and holding the brake (flat velocity while braking is normal, not just at speed) — fixed by exempting near-zero starting velocity, and now regression-tested against that scenario explicitly.
