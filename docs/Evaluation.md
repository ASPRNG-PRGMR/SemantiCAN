# Evaluation - SemantiCAN

**Status:** Draft v0.1 - skeleton only. This document will be populated with real measurements in Phase 5 of the roadmap; right now it defines *what* will be measured and *how*, so evaluation isn't an afterthought.

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

First real numbers, from `scripts/evaluate_replay.py` against a recorded 15-second run (`backend/sim/record.py`, standard scenario: `ECU_SPEED`/`ECU_BRAKE`/`ECU_STEER` injected at t=5s, 3,616 total messages). Run in an environment without `torch` installed, so these numbers reflect the rule engine only — the LSTM columns need re-running on a machine with torch to be meaningful.

### 4.1 Detection Accuracy
100% (16/16 attack messages flagged) against the standard blatant-attack scenario.

### 4.2 False Positive Rate
0% (0/3,600 normal messages flagged).

### 4.3 Detection Delay
0.0s for all three attack ECUs — the standard scenario's payloads (e.g. velocity=180, accel=−12) cross a rule threshold on the very first attack message, so there's no meaningful lag to measure with this scenario.

### 4.4 Rule Hits vs. LSTM Hits
16/16 rule-only, 0 LSTM-only, 0 both (torch unavailable in the environment these numbers were generated in — needs re-running with the LSTM active).

**This result is itself informative, not just a clean pass:** 100% accuracy with 0 LSTM contribution on the standard scenario means the current attack payloads are too blatant to say anything about whether the LSTM (or the fusion architecture generally) is doing real work. `TARA-04` (slow semantic drift, sub-threshold spoofing) is the scenario that would actually test this, and is still open - see `Phase3_Plan.md`.

A second evaluation, `scripts/evaluate_consistency.py`, tests the Cross-ECU Correlation feature specifically: a coordinated attack crafted to individually pass all four existing per-ECU rules (see `Detection.md` §8.2) produces 0/N detections from the rule engine and is caught by the Consistency Engine on the first qualifying window. Two legitimate control scenarios (braking to a stop, holding the brake at a stoplight) produced 0 false positives from the Consistency Engine after one FP bug found during testing was fixed.

## 5. Limitations of the Evaluation Itself

To be filled in alongside results - anticipated candidates include: small/fixed set of attack scenarios (only 3 attack ECUs), single shared LSTM model rather than per-ECU models, and simulation-only telemetry rather than real CAN bus captures.
