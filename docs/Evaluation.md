# Evaluation - SemantiCAN

**Status:** Draft v0.3 - populated with real measurements. §4 now holds numbers from a run with `torch` actually installed, which is what every previous version of this section was explicitly waiting on. The headline figures are also surfaced in the dashboard's Evaluation tab (`frontend/dashboard/reference.py`).

## 1. Why Evaluate

A demo shows that detection works on the built-in attack scenarios. Evaluation shows *how well* it works, *where it fails*, and *what the tradeoffs are* - the difference between a proof-of-concept and an engineering result. This is one of the highest-leverage additions to the project per the roadmap's priority summary.

## 2. Metrics to Collect

| Metric | Definition | Why it matters |
|---|---|---|
| **Detection Accuracy** | Fraction of injected attack messages correctly flagged (by rules, LSTM, or fused score) | Core measure of whether the system does its job |
| **False Positive Rate** | Fraction of normal ECU messages incorrectly flagged as anomalous | High FP rate makes the SOC dashboard unusable in practice - analysts will start ignoring alerts |
| **Detection Delay** | Time (or message count) between attack injection and first alert | Matters for how quickly an operator or downstream system could react |
| **Rule Hits vs. LSTM Hits** | Breakdown of which detector(s) fired for each true-positive alert | Shows whether the two-detector fusion design is actually earning its complexity, per the rationale in `Architecture.md` §5 |
| **LSTM Training Time / Sample Count** | Wall-clock time and sample count to reach `● LSTM Ready` | Relevant to the "no warm-up coverage" gap described in `Threat_Model.md` |

## 3. Methodology (planned)

1. **Baseline run** - run the simulation with no attack ECUs injected; record false-positive rate over a fixed duration.
2. **Standard attack run** - run the default simulation (`ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER` injected at 10 s) multiple times; record detection accuracy and delay per ECU.
3. **Detector attribution** - for each true positive, record whether the rule engine, the LSTM, or both fired, to fill in the "Rule Hits vs. LSTM Hits" metric.
4. **Repeat with Attack Replay** (once implemented, see `Future_Work.md`) - store telemetry from a run, replay it, and compare before/after detection behavior. This supports regression testing as detection logic changes.

## 4. Results

### 4.0 Two runs, and why both are listed

Every earlier number in this section was produced in an environment with no `torch` installed. `backend/ai/advisor.py` has no fallback path by design, so in that environment it returns `0.0` for every message: the LSTM columns were not "zero because the LSTM found nothing", they were zero because the LSTM was never running. That made the fusion architecture — the project's main technical claim — untested.

The run below was made on a machine with `torch 2.14.0`. The pre-torch figures are kept alongside it because the difference between the two is itself the result.

**Run:** `scripts/evaluate_replay.py` against `backend/recordings/run_torch_001` — 3,616 messages over 15s, `ECU_SPEED`/`ECU_BRAKE`/`ECU_STEER` injected at t=5s. 2026-09-05.

The recording itself is not committed — it is ~740 KB of regenerable telemetry. To reproduce these numbers from scratch, from the project root with `torch` installed:

```bash
python -m backend.sim.record --output backend/recordings/run_torch_001 --duration 15 --attack-delay 5
python scripts/evaluate_replay.py --run backend/recordings/run_torch_001 --speed 0
python scripts/evaluate_consistency.py
python scripts/evaluate_subthreshold.py --duration 60 --ghost-delay 10
```

Message counts and the exact false-positive figure will vary slightly between runs, since the normal ECUs are seeded randomly. The conclusions in §4.4 and §4.5 — the LSTM contributing no true positives on the standard scenario, and not separating `ECU_GHOST` from normal traffic — are what should be re-checked, not the third decimal place.

| Metric | Rules only (no torch) | Rules + LSTM (torch 2.14.0) |
|---|---|---|
| Detection accuracy | 100% (16/16) | **100% (16/16)** |
| False positive rate | 0% (0/3,600) | **0.11% (4/3,600)** |
| Detection delay | 0.0s, all three ECUs | **0.0s, all three ECUs** |
| Rule-only / LSTM-only / both | 16 / 0 / 0 | **16 / 0 / 0** |

### 4.1 Detection Accuracy
100% (16/16 attack messages flagged). Unchanged by enabling the LSTM.

### 4.2 False Positive Rate
0.11% (4/3,600 normal messages flagged), up from 0%. All four came from the LSTM.

### 4.3 Detection Delay
0.0s for all three attack ECUs. The standard scenario's payloads (velocity=180, accel=−12) cross a rule threshold on the very first attack message, so there is no meaningful lag to measure with this scenario.

### 4.4 Rule Hits vs. LSTM Hits
16 rule-only, 0 LSTM-only, 0 both — with the LSTM trained and running.

**This is the result, and it is not a good one for the fusion argument.** With both detectors live, the LSTM contributed zero true positives and four false positives. On this scenario the second detector is a net negative. That is not by itself an argument for removing it: the attack payloads are blatant enough that the rules were always going to win, so the standard scenario cannot distinguish "the LSTM is not useful" from "the LSTM was never needed here". What it does establish is that **the standard scenario cannot be cited as evidence that detector fusion earns its complexity** — a claim earlier drafts of this document came close to making on the strength of numbers produced without the model running at all.

### 4.5 Sub-threshold attack (TARA-04)
**Run:** `scripts/evaluate_subthreshold.py --duration 60 --ghost-delay 10`, torch 2.14.0, LSTM trained.

| Detector | Result |
|---|---|
| Per-ECU rules on `ECU_GHOST` | 0 fires (expected — structurally blind by construction) |
| Consistency Engine involving `ECU_GHOST` | 0 fires (expected — `ECU_GHOST` is outside `CORRELATED_ECU_IDS`) |
| LSTM confidence, `ECU_GHOST` | n=90, mean 53.2, max 100.0 |
| LSTM confidence, `ECU_001` (normal control) | n=110, mean 48.1, max 100.0 |

A 5-point difference in means with both ECUs saturating at 100.0 is not a detection. **TARA-04 remains open, and is now open on the basis of a measurement rather than an assumption.** The detector specifically intended to cover the sub-threshold gap does not currently separate the sub-threshold attack from normal traffic. Two candidate explanations are worth testing before concluding the approach is wrong: the training buffer in `advisor.py` is a flat list filled by whichever ECU publishes next, so training windows mix ECUs even though inference windows are correctly per-ECU; and a single shared model across 120 ECUs may not have the capacity to represent per-ECU normality at all.

### 4.6 Cross-ECU Correlation (TARA-05)
**Run:** `scripts/evaluate_consistency.py`, default 12s, stealth attack from t=3s.

A coordinated attack holding `brake_pressure=0.92` with flat velocity, crafted to pass every per-ECU rule individually, produced **0 fires from all four per-ECU rules** — none of them reads `brake_pressure` at all — and **51 Consistency Engine findings**, the first at t=3.5s (0.5s after the attack began) at confidence 72.0. Two legitimate control scenarios (braking to a stop, holding the brake at a stoplight) produced 0 false positives.

This is the one place where the second detection stage demonstrably catches something the first cannot.

## 5. Limitations of the Evaluation Itself

- **Small, fixed scenario set.** Three attack ECUs plus one sub-threshold ghost. Detection accuracy of 100% describes those scenarios, not the space of semantic attacks.
- **The standard scenario is too blatant to discriminate between detectors** (§4.4). Any conclusion about fusion needs harder scenarios.
- **Single shared LSTM across 120 ECUs**, trained on an ECU-interleaved buffer (§4.5). Per-ECU models are untested.
- **Simulation-only telemetry.** No real CAN bus captures, so the definition of "normal" is the simulator's, not a vehicle's.
- **Single run per scenario.** The figures above are not averaged over repeats and carry no variance estimate.
