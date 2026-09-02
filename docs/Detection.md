# Detection - SemantiCAN

**Status:** Draft v0.1 - describes current detection logic. ISO 21434-style rule mapping (Rule → Protects → Threat → Security Goal) will be added here in Phase 2 Step 3.

## 1. Detection Philosophy

SemantiCAN does not attempt to detect malformed packets, protocol abuse, or unusual CAN IDs - that is the domain of a conventional network-layer IDS. Instead, it assumes messages are **syntactically valid** and asks a different question: *is the content of this message physically and statistically plausible, given the rest of the vehicle's telemetry?*

Two complementary methods answer that question:

| Method | What it catches |
|---|---|
| Physics rules | Hardcoded physical impossibilities (instant velocity, impossible deceleration) |
| LSTM model | Subtle distributional drift - values that look individually plausible but deviate from the normal joint pattern |

## 2. Physics-Based Rules (`backend/core/checks.py`, `constraints.py`)

| Rule | Trigger condition | Severity |
|---|---|---|
| `velocity_without_acceleration` | Velocity > 140 km/h with reported accel < 1 m/s² | HIGH |
| `impossible_acceleration` | Absolute acceleration > 7 m/s² | CRITICAL |
| `unsafe_steering_angle` | Steering > 30° at speed > 80 km/h | MEDIUM |
| `acceleration_velocity_mismatch` | Reported accel vs. derived accel (Δv/Δt) differ by > 2 m/s² | HIGH |

Each rule is intentionally simple and explainable: a violation can be pointed to and justified without reference to a model's internal state. This directly supports the Explainability security goal in `Threat_Model.md`.

### 2.1 Rule → Threat Mapping

Each rule is now tied to a formal TARA entry (see `TARA.md`) rather than described in isolation.

| Rule | Protects | Threat | Security Goal |
|---|---|---|---|
| `velocity_without_acceleration` | Vehicle telemetry integrity | TARA-01 - Spoofed Speed ECU | Maintain telemetry integrity |
| `impossible_acceleration` | Vehicle telemetry integrity | TARA-01 - Spoofed Speed ECU, TARA-02 - Spoofed Brake ECU | Maintain telemetry integrity |
| `unsafe_steering_angle` | Vehicle directional-control integrity | TARA-03 - Spoofed Steering ECU | Prevent hazardous steering commands |
| `acceleration_velocity_mismatch` | Vehicle telemetry integrity | TARA-01 - Spoofed Speed ECU | Maintain telemetry integrity |

Not yet covered by any rule (tracked in `TARA.md` §2 and `Future_Work.md`):

| Gap | Related TARA entry |
|---|---|
| Sub-threshold / slow semantic drift | TARA-04 (currently addressed only by LSTM, unquantified) |
| Battery/BMS, timing, and other untargeted anomaly types | TARA-05 - Rule Threshold Blind Spots |
| Message-origin / ECU identity spoofing | TARA-08 - Spoofed ECU Identity |

## 3. LSTM Anomaly Detection (`backend/ai/advisor.py`)

The LSTM runs entirely on-device - no cloud dependency, no API key - and operates in three phases.

### 3.1 Phase 1 - Baseline collection (0–10 s)
Normal ECU messages (velocity, acceleration, steering angle) are buffered into a rolling sample store. The dashboard shows `◌ LSTM Training (N samples)`.

### 3.2 Phase 2 - Training
Once 300 normal samples are collected, a two-layer LSTM is trained to predict the next telemetry vector from a sliding window of 20 timesteps. Training runs in a background thread and takes a few seconds on CPU.

### 3.3 Phase 3 - Inference
For every new message, the model predicts the expected next telemetry step and computes reconstruction error. High error translates to a high anomaly confidence score (0–100). The dashboard badge switches to `● LSTM Ready`.

### 3.4 Tunable Constants

| Constant | Default | Description |
|---|---|---|
| `WINDOW_SIZE` | 20 | Timesteps per inference window |
| `TRAIN_STEPS` | 300 | Normal samples before first training |
| `RETRAIN_EVERY` | 500 | Retrain every N steps after initial fit |
| `HIDDEN_DIM` | 32 | LSTM hidden size |
| `NUM_LAYERS` | 2 | LSTM depth |

### 3.5 Known Limitation: Baseline Trust
The LSTM's definition of "normal" is only as trustworthy as the samples it trains on. The current prototype assumes the baseline window is attack-free (see `Threat_Model.md` §5). This is a known gap, not a hidden one.

## 4. Score Fusion (`backend/core/scoring.py`)

```
fused_confidence = max(rule_based_confidence, lstm_confidence)
```

Either detector alone can trigger an alert:
- The rule engine catches blatant physical violations immediately, even before the LSTM is trained.
- The LSTM catches subtler drift that no fixed threshold would catch.

This design choice is the primary technical argument for resilience to single-vector evasion (Security Goal 3 in `Threat_Model.md`).

## 5. Alert Generation (`backend/core/alerts.py`)

Alerts are generated per-ECU, deduplicated, and include: violated rule(s) or anomaly score, severity, confidence, and a timestamp. Alerts feed both the in-memory rolling store (60 s window, used by the dashboard) and the persisted log (`backend/logs/alerts.log`).

## 6. Vehicle-Wide Risk Scoring (`backend/core/vehicle_risk.py`)

Individual ECU alerts are aggregated into a single vehicle risk score, weighted by ECU criticality (1–5 scale, `backend/core/ecu_registry.py`). This lets a more critical ECU (e.g., steering) contribute more to the overall risk signal than a less critical one, for the same confidence score.

## 7. Current Attack Scenarios (Simulation)

| ECU | Payload | Detection method |
|---|---|---|
| `ECU_SPEED` | velocity=180 km/h, accel=−12 m/s² | Rules: `impossible_acceleration`, `acceleration_velocity_mismatch` |
| `ECU_BRAKE` | brake=0.95, velocity=160 km/h, accel=8.5 m/s² | Rules: `impossible_acceleration` + LSTM drift |
| `ECU_STEER` | steering=55°, velocity=100 km/h | Rules: `unsafe_steering_angle` |

## 8. Detection Improvements — Implementation Status

**Attack Replay** (`backend/sim/recorder.py`, `replayer.py`, `record.py`, `replay.py`) and **Cross-ECU Correlation** (`backend/core/consistency.py`) are implemented. **Replay Attack Detection** remains planned; full specification in `Phase3_Plan.md` §2.

### 8.1 Attack Replay
Records a full run (normal + attack traffic) to `telemetry.jsonl` plus a `ground_truth.jsonl` sidecar (kept structurally separate so ground truth can never leak into a replayed run), and replays it through the real detection pipeline for evaluation. `scripts/evaluate_replay.py` computes Detection Accuracy, False Positive Rate, Detection Delay, and Rule-vs-LSTM attribution directly from a recording — this is what populated `Evaluation.md` §4's first real numbers. One bug was caught and fixed during implementation: `backend/sim/bus.py`'s `MessageBus` originally handed every subscriber of a topic the same underlying queue, meaning two subscribers to one topic (the detector and the recorder) would have silently split messages between them rather than both receiving every message. Fixed to properly fan out to each subscriber independently.

### 8.2 Cross-ECU Correlation (Consistency Engine)
A second detection stage, running alongside (not replacing) the existing per-ECU rules, reasoning jointly across `ECU_SPEED`, `ECU_BRAKE`, and `ECU_STEER`. Three checks: Speed-Brake Consistency (sustained high brake pressure without a corresponding velocity decrease), Speed-Steering-Acceleration Consistency (a sustained hard turn at speed with no corresponding acceleration signature), and Cross-ECU Timing Consistency (publish-interval skew across the three correlated ECUs).

This closes a gap that isn't hypothetical: `backend/core/checks.py`'s four existing rules never inspect the `brake_pressure` field at all. `scripts/evaluate_consistency.py` demonstrates this directly — a coordinated attack (`backend/sim/node_stealth.py`) holds `brake_pressure=0.92` while keeping velocity, acceleration, and steering angle individually well under every existing rule's threshold. Result: 0 detections from the four existing rules, 100% detection from the Consistency Engine. The same script, run against two legitimate scenarios (braking to a full stop, and holding the brake at a stoplight), produces 0 false positives — though the first version of the Speed-Brake check did false-positive on "stopped and holding the brake," since a vehicle already at rest has flat velocity by definition; this was caught in testing and fixed by exempting near-zero starting velocity from the check.

Findings are attributed to the vehicle as a whole (synthetic `VEHICLE_CONSISTENCY::<finding_type>` id) rather than a single ECU, and feed into `Vehicle Risk Engine` scoring via the existing `score_violations` function, since a finding here already means multiple ECUs are jointly describing something physically impossible.

Not yet covered by any rule (tracked in `TARA.md` §2 and `Future_Work.md`):

| Gap | Related TARA entry |
|---|---|
| Sub-threshold / slow semantic drift | TARA-04 (currently addressed only by LSTM, unquantified — see `Phase3_Plan.md` for the planned adversarial scenario to test this directly) |
| Battery/BMS, timing, and other untargeted anomaly types beyond the three correlated ECUs | TARA-05 (partially addressed — see above) |
| Message-origin / ECU identity spoofing | TARA-08 - Spoofed ECU Identity |
| Replay of previously-legitimate telemetry | TARA-09 - planned, see `Phase3_Plan.md` §2 |
