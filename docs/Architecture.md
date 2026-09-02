# Architecture - SemantiCAN

**Status:** Draft v0.1 - describes the current implementation. Will be updated as Phase 2 (security architecture framing) and Phase 3 (technical improvements) land.

## 1. Overview

SemantiCAN is a simulation platform for detecting **semantically inconsistent ECU telemetry** - messages that are protocol-valid but physically implausible or statistically anomalous. It combines a rules engine with a locally-trained LSTM model, fuses their outputs, and surfaces the result through a Flask API and a Dash-based SOC-style dashboard.

The current implementation runs entirely in-process (single machine, no external network dependency, no cloud API key required).

## 2. High-Level Data Flow

```
Vehicle
  |
  v
Message Bus
  |
  v
Semantic Integrity Controller
  |
  v
Risk Engine
  |
  v
SOC Dashboard
```

This is the security-relevant framing of the pipeline. The implementation-level view (below) shows the same flow with the concrete components involved.

## 3. Implementation-Level Diagram

```
                   +----------------------+
                   |  Normal ECU Nodes    |  <- 120 simulated ECUs
                   +----------+-----------+
                              |
                   +----------------------+
                   |  Attack ECU Nodes    |  <- injected after 10 s
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   |    Message Bus       |  <- in-process pub/sub
                   +----------+-----------+
                              |
                              v
                   +------------------------------+
                   | Semantic Integrity Controller |
                   |------------------------------|
                   | Feature Extraction            |
                   | Physics Rule Checks           | <- rules-based (per-ECU)
                   | LSTM Anomaly Scoring          | <- ML-based (local, per-ECU)
                   | Consistency Engine            | <- rules-based (cross-ECU)
                   | Score Fusion (max)            |
                   | Alert Generation               |
                   +----------+-----------+-------+
                              |
              +---------------+------------------+
              |                                  |
              v                                  v
    +----------------------+        +---------------------------+
    | Vehicle Risk Engine  |        | Flask Backend API          |
    | LSTM Advisory Layer  |        |---------------------------|
    | Alert Store          |        | /api/summary               |
    +----------------------+        | /api/alerts                |
                                    | /api/semantic-history      |
                                    | /api/violation-rate        |
                                    | /api/top-anomalous-ecus    |
                                    | /api/lstm-status           |
                                    +-------------+-------------+
                                                  |
                                                  v
                                    +---------------------------+
                                    |   Dash SOC Dashboard       |
                                    +---------------------------+
```

## 4. Component Descriptions

### 4.1 Normal / Attack ECU Nodes (`backend/sim/`)
Simulates 120 normal ECUs publishing plausible telemetry (velocity, acceleration, steering angle) on a fixed interval. After a configurable delay (default 10 s, `backend/sim/sim.yaml`), three attack ECUs (`ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER`) begin publishing physically inconsistent payloads. Every ECU, whether normal or attack, is treated by the controller as an untrusted input source - see `Threat_Model.md` §7.

**Why it exists:** provides a controlled, repeatable telemetry stream so detection behavior can be evaluated without real vehicle hardware.

### 4.2 Message Bus (`backend/sim/bus.py`)
An in-process pub/sub queue that decouples ECU publishers from the controller. In a real deployment this boundary maps to a CAN / CAN-FD bus or automotive Ethernet segment.

**Why it exists:** isolates the simulation/ingestion layer from the detection layer, so the detection logic doesn't need to know how telemetry physically arrived.

### 4.3 Semantic Integrity Controller (`backend/core/`, `backend/ai/`)
The core detection component, composed of:

- **Feature Extraction** (`features.py`) - derives features such as Δv/Δt acceleration from raw telemetry.
- **Physics Rule Checks** (`checks.py`, `constraints.py`) - hardcoded physical-impossibility and unsafe-combination rules (see `Detection.md`).
- **LSTM Anomaly Scoring** (`ai/advisor.py`) - a locally-trained two-layer LSTM that scores reconstruction error against a learned baseline of normal telemetry.
- **Score Fusion** (`scoring.py`) - combines rule-based and LSTM-based confidence via `max(rule_confidence, lstm_confidence)`, so either method alone can trigger an alert.
- **Alert Generation** (`alerts.py`) - deduplicates and emits per-ECU alerts.

**Why it exists:** this is the security-relevant core of the system - the point where untrusted telemetry is evaluated against both deterministic and learned models of "normal."

### 4.3.1 Consistency Engine (`backend/core/consistency.py`)
A second detection stage, reasoning jointly across `ECU_SPEED`, `ECU_BRAKE`, and `ECU_STEER` rather than one ECU's message in isolation. Runs on every message from a correlated ECU regardless of whether the per-ECU rules above fired on that same message. Findings are attributed to the vehicle as a whole (a synthetic `VEHICLE_CONSISTENCY::<finding_type>` id), not to a single ECU, and are scored via the same `score_violations` function used for per-ECU rules.

**Why it exists:** closes TARA-05 (rule threshold blind spots) - concretely, none of the four per-ECU rules in `checks.py` ever inspect the `brake_pressure` field, so an attacker holding brake pressure high while keeping every other value individually unremarkable passes every existing rule untouched. See `Detection.md` §8.2 and `scripts/evaluate_consistency.py` for a demonstrated before/after result.

### 4.4 Vehicle Risk Engine (`backend/core/vehicle_risk.py`, `backend/core/ecu_registry.py`)
Aggregates individual ECU alerts into a single, criticality-weighted vehicle-wide risk score, using per-ECU weights (1–5 scale) defined in `ecu_registry.py`.

**Why it exists:** an operator needs a single top-line signal, not 120 independent per-ECU indicators - this component answers "how much should I trust this vehicle right now."

### 4.5 LSTM Advisory Layer (`backend/ai/advisor.py`)
Beyond scoring, the advisor generates a SOC-style natural-language narrative for each alert (vehicle-wide risk, anomalous ECU list, violation types, recommended escalation actions), surfaced in the dashboard's AI Advisory panel.

**Why it exists:** bridges raw scores and analyst-usable context, similar to how SIEM tooling in a real SOC augments raw alerts with narrative.

### 4.6 Alert Store
An in-memory rolling store (60-second window, see `api_state.py`) plus a persisted log (`backend/logs/alerts.log`).

**Why it exists:** supports both the live dashboard (recent window) and after-the-fact review (persisted log) - see `Threat_Model.md` for why auditability is a stated security goal.

### 4.7 Flask Backend API (`backend/api.py`, `backend/api_state.py`)
Exposes six read-only JSON endpoints (`/api/summary`, `/api/alerts`, `/api/semantic-history`, `/api/violation-rate`, `/api/top-anomalous-ecus`, `/api/lstm-status`). Currently unauthenticated - see `Threat_Model.md` §7 for the associated trust-boundary gap.

**Why it exists:** decouples the detection/simulation process from the presentation layer, and models how a real vehicle security operations backend would expose state to a SOC tool.

### 4.8 Dash SOC Dashboard (`frontend/dashboard/`)
Polls the backend API and renders: a KPI strip, an LSTM training/ready badge, per-ECU confidence history, a violation-rate bar chart, the AI Advisory narrative, top anomalous ECUs, and active alert cards.

**Why it exists:** demonstrates how the detection signal would actually be consumed by a human analyst, not just logged.

## 5. Design Rationale: Why Two Detectors

The rules engine and the LSTM are intentionally complementary rather than redundant:

- **Rules** catch blatant physical violations immediately, with no warm-up period, and are fully explainable (a specific threshold was crossed).
- **LSTM** catches subtler distributional drift - telemetry that looks individually plausible but deviates from the learned joint pattern across ECUs over time - at the cost of a training/warm-up period and reduced interpretability.

Fusing via `max()` means an attacker has to simultaneously evade both a deterministic, auditable rule set and a learned model of normal joint behavior to go undetected - this is the core resilience argument referenced as Security Goal 3 in `Threat_Model.md`.

## 6. Known Architectural Gaps

These are tracked here so they can be addressed deliberately rather than silently:

- No authentication/authorization between the dashboard and the backend API.
- No cryptographic verification of ECU message origin - the controller trusts the `ECU_ID` field.
- The LSTM baseline window is assumed attack-free; there is no mechanism yet to detect a poisoned baseline.
- Single shared LSTM model across all ECUs, rather than per-ECU models (noted in the README's future-improvements list).
- The Consistency Engine (§4.3.1) currently only correlates `ECU_SPEED`/`ECU_BRAKE`/`ECU_STEER`; other ECU combinations (e.g. battery/BMS-related) have no cross-ECU coverage yet.

~~The message bus handed every subscriber of a topic the same underlying queue.Queue, so two simultaneous subscribers to one topic were competing consumers rather than independent fan-out subscribers.~~ Fixed - `backend/sim/bus.py`'s `MessageBus` now hands each subscriber its own queue and fans every published message out to all of them. This was found and fixed while building Attack Replay (`backend/sim/recorder.py`), which is exactly the kind of second subscriber that would have silently broken detection under the old behavior.

See `Future_Work.md` for how the remaining gaps are prioritized.
