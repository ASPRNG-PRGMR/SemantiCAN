# SemantiCAN — EV Semantic Integrity Monitor

### Automotive Cybersecurity · Vehicle Telemetry Anomaly Detection · SOC Dashboard

An automotive cybersecurity simulation platform that detects **semantic anomalies in ECU telemetry** and visualises them through a live SOC-style dashboard.

The system monitors vehicle networks not just for malformed packets or protocol abuse, but for **physically inconsistent or suspicious telemetry values** that may indicate compromised ECUs, spoofed telemetry, or semantic data injection attacks. Anomaly detection is powered by a **locally-trained LSTM model** — no external API or cloud key required.

---

## Why this matters

Most IDS solutions in automotive networks focus on CAN IDs, packet signatures, malformed frames, or unusual traffic patterns. But a sophisticated attacker may still send **perfectly valid-looking messages** carrying **unsafe or physically impossible values**.

**Example:**
- Vehicle reports **180 km/h**
- While also reporting **−12 m/s² acceleration**
- Or a steering angle that is unsafe for the current speed

These messages are syntactically valid — but **semantically suspicious**.

This project detects exactly that layer, using two complementary methods:

| Method | What it catches |
|---|---|
| Physics rules | Hardcoded physical impossibilities (instant velocity, impossible decel) |
| LSTM model | Subtle distributional drift — values that look individually plausible but deviate from the normal joint pattern |

---

## Architecture

```
                   +----------------------+
                   |  Normal ECU Nodes    |  ← 120 simulated ECUs
                   +----------+-----------+
                              |
                   +----------------------+
                   |  Attack ECU Nodes    |  ← injected after 10 s
                   +----------+-----------+
                              |
                              v
                   +----------------------+
                   |    Message Bus       |  ← in-process pub/sub
                   +----------+-----------+
                              |
                              v
                   +------------------------------+
                   | Semantic Integrity Controller |
                   |------------------------------|
                   | Feature Extraction           |
                   | Physics Rule Checks          | ← rules-based
                   | LSTM Anomaly Scoring         | ← ML-based (local)
                   | Score Fusion (max)           |
                   | Alert Generation             |
                   +----------+-----------+-------+
                              |
              +---------------+------------------+
              |                                  |
              v                                  v
    +----------------------+        +---------------------------+
    | Vehicle Risk Engine  |        | Flask Backend API         |
    | LSTM Advisory Layer  |        |---------------------------|
    | Alert Store          |        | /api/summary              |
    +----------------------+        | /api/alerts               |
                                    | /api/semantic-history     |
                                    | /api/violation-rate       |
                                    | /api/top-anomalous-ecus   |
                                    | /api/lstm-status          |
                                    +-------------+-------------+
                                                  |
                                                  v
                                    +---------------------------+
                                    |   Dash SOC Dashboard      |
                                    +---------------------------+
```

---

## LSTM Anomaly Detection

The LSTM runs entirely on-device — no cloud dependency, no API key. It operates in three phases:

### Phase 1 — Baseline collection (0–10 s)
Normal ECU messages (velocity, acceleration, steering angle) are buffered into a rolling sample store. The dashboard shows `◌ LSTM Training (N samples)`.

### Phase 2 — Training
Once **300 normal samples** are collected, a two-layer LSTM is trained to predict the next telemetry vector from a sliding window of 20 timesteps. Training runs in a background thread and takes a few seconds on CPU.

### Phase 3 — Inference
For every new message, the model predicts the expected next telemetry step and computes reconstruction error. High error translates to a high anomaly confidence score (0–100). The dashboard badge switches to `● LSTM Ready`.

### Score fusion
The final confidence score for each ECU is:

```
fused_confidence = max(rule_based_confidence, lstm_confidence)
```

This means either detector alone can trigger an alert:
- The **rule engine** catches blatant physical violations immediately, even before the LSTM is trained.
- The **LSTM** catches subtler drift — values that are individually plausible but deviate from the normal joint distribution.

### Tunable constants (`backend/ai/advisor.py`)

| Constant | Default | Description |
|---|---|---|
| `WINDOW_SIZE` | 20 | Timesteps per inference window |
| `TRAIN_STEPS` | 300 | Normal samples before first training |
| `RETRAIN_EVERY` | 500 | Retrain every N steps after initial fit |
| `HIDDEN_DIM` | 32 | LSTM hidden size |
| `NUM_LAYERS` | 2 | LSTM depth |

### Advisory text
After training, the LSTM advisor also generates a SOC-style narrative for each alert. This text appears in the **AI Advisory** panel on the dashboard and includes vehicle-wide risk score, anomalous ECU list, detected violation types, and recommended escalation actions.

---

## Detection rules

| Rule | Trigger condition | Severity |
|---|---|---|
| `velocity_without_acceleration` | Velocity > 140 km/h with reported accel < 1 m/s² | HIGH |
| `impossible_acceleration` | Absolute acceleration > 7 m/s² | CRITICAL |
| `unsafe_steering_angle` | Steering > 30° at speed > 80 km/h | MEDIUM |
| `acceleration_velocity_mismatch` | Reported accel vs derived accel (Δv/Δt) differ by > 2 m/s² | HIGH |

---

## Evaluation

Measured against a recorded 15-second run (3,616 messages, attacks injected at t=5s) with `torch` installed and the LSTM trained. Full method, caveats and reproduction commands in `docs/Evaluation.md`.

| Metric | Rules only | Rules + LSTM |
|---|---|---|
| Detection accuracy | 100% (16/16) | **100% (16/16)** |
| False positive rate | 0% (0/3,600) | **0.11% (4/3,600)** |
| Detection delay | 0.0s, all three attack ECUs | **0.0s** |
| Rule-only / LSTM-only / both | 16 / 0 / 0 | **16 / 0 / 0** |

Two results matter more than the pass marks:

- **On the standard scenario the LSTM contributed zero true positives and four false positives.** That is not an argument for removing it — the attack payloads cross a rule threshold on their first message, so the rules were always going to win — but it does mean this scenario cannot be cited as evidence that detector fusion earns its complexity.
- **The sub-threshold attack (TARA-04) is not detected by anything.** The rules and the Consistency Engine are structurally blind to it by construction, and the LSTM scored the attacking ECU at mean 53.2 against a normal ECU's 48.1, both saturating at 100. The detector meant to close that gap does not currently close it.

The one place the second detection stage demonstrably earns itself is cross-ECU correlation: a coordinated attack holding `brake_pressure=0.92` with flat velocity produces **0 fires from all four per-ECU rules** — none of them reads `brake_pressure` — and is caught by the Consistency Engine 0.5s in, with 0 false positives across two legitimate control scenarios.

---

## Project structure

```
SemantiCAN/
│
├── backend/
│   ├── main.py               ← Orchestration: bus → detection → alert loop
│   ├── api.py                ← Flask API (6 endpoints)
│   ├── api_state.py          ← In-memory rolling state (60 s window)
│   │
│   ├── ai/
│   │   └── advisor.py        ← Local LSTM model + SOC advisory text generator
│   │
│   ├── core/
│   │   ├── alerts.py         ← Alert generation and per-ECU deduplication
│   │   ├── checks.py         ← Physics-based semantic rules
│   │   ├── consistency.py    ← Cross-ECU Consistency Engine
│   │   ├── constraints.py    ← Physics helper functions
│   │   ├── ecu_registry.py   ← ECU criticality weights (1–5) + domain roles
│   │   ├── features.py       ← Derived feature extraction (Δv/Δt acceleration)
│   │   ├── scoring.py        ← Rule violation → severity + confidence score
│   │   └── vehicle_risk.py   ← Criticality-weighted vehicle risk score
│   │
│   ├── sim/
│   │   ├── bus.py            ← In-memory pub/sub message bus
│   │   ├── ecu_ids.py        ← 120 ECU IDs
│   │   ├── node_normal.py    ← Normal ECU telemetry publisher
│   │   ├── node_attack.py    ← Attack ECU injector (3 ECUs)
│   │   └── sim.yaml          ← Simulation config (attack delay)
│   │
│   ├── security/
│   │   └── env.py            ← Safe .env loader (optional)
│   │
│   └── logs/
│       └── alerts.log        ← Persisted alert log (auto-created)
│
├── frontend/
│   ├── config.py             ← API base URL, refresh interval, thresholds
│   ├── DESIGN_NOTES.md       ← Console design decisions and the API quirks behind them
│   │
│   └── dashboard/
│       ├── app.py            ← Dash app entrypoint
│       ├── layout.py         ← Static page structure (only filled by callbacks)
│       ├── callbacks.py      ← Live callbacks (pulls from Flask API)
│       ├── reference.py      ← Rule → TARA mapping + evaluation figures (Detection/Evaluation views)
│       └── assets/
│           ├── style.css     ← Light + dark themes, soft-depth surfaces
│           └── motion.js     ← Animation state keyed by alert_id, risk gauge tween
│
├── scripts/
│   ├── run_backend.py        ← Launch backend (detection + API)
│   ├── run_dashboard.py      ← Launch Dash console
│   ├── run_attack.py         ← Manual one-shot attack injection
│   ├── evaluate_replay.py    ← Detection accuracy / FP rate / delay / attribution
│   ├── evaluate_consistency.py       ← Cross-ECU Consistency Engine (TARA-05)
│   └── evaluate_subthreshold.py      ← Sub-threshold attack (TARA-04)
│
├── docs/                     ← Threat model, TARA, architecture, detection, evaluation
│
├── requirements.txt
├── .env.example              ← Optional: no keys needed
└── README.md
```

---

## Quick start

### 1. Clone

```bash
git clone https://github.com/ASPRNG-PRGMR/EdgeRover
cd SemantiCAN
```

### 2. Create a virtual environment

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

No API keys needed. The system is fully self-contained.

### 4. Run the backend

**Important: always run scripts from the project root.**

```bash
python scripts/run_backend.py
```

Expected output:

```
[*] Semantic Integrity Domain Controller started
[*] Backend API running on http://127.0.0.1:5000
[*] Normal ECU simulation started (120 ECUs)
[*] LSTM advisor collecting baseline — attacks inject in 10 s ...
[LSTM Advisor] Model trained on 280 windows
[!] Attack ECUs injected (ECU_SPEED, ECU_BRAKE, ECU_STEER)
[ALERT] ECU_SPEED | severity=critical | confidence=95 | lstm=0
[ALERT] ECU_STEER | severity=medium   | confidence=60 | lstm=0
[ALERT] ECU_BRAKE | severity=low      | confidence=0  | lstm=72
```

### 5. Run the dashboard

Open a second terminal (with the venv activated), from the project root:

```bash
python scripts/run_dashboard.py
```

Open your browser at:

```
http://127.0.0.1:8050
```

---

## API reference

All endpoints return JSON.

| Endpoint | Description |
|---|---|
| `GET /api/summary` | Active ECU count, anomalous ECU count, last anomaly timestamp |
| `GET /api/semantic-history` | Rolling 60-second confidence history per ECU |
| `GET /api/violation-rate` | Anomaly counts in 10-second time buckets |
| `GET /api/alerts` | All active alerts with violations, severity, and advisory text |
| `GET /api/top-anomalous-ecus` | Top 3 highest-risk ECUs. **Not used by the console** — it sorts by `(risk, last_seen)` and caps at three, so once many ECUs sit at the ceiling together the "top three" is whichever three reported most recently. The console derives that panel from `/api/semantic-history` so it can detect the tie and say so. |
| `GET /api/detector-breakdown` | Counts of active alerts by which detector caught them (`rule` / `lstm` / `both` / `unknown`) |
| `GET /api/lstm-status` | LSTM training state: `trained` (bool), `samples` collected, `train_steps` run. Returns HTTP 500 with `{"error": ...}` if the advisor cannot be imported |

`/api/summary`'s `last_anomaly` field is **not** the last anomaly: in `get_summary()` it is `semantic_history[-1]["timestamp"]`, the newest message from any ECU. It is a feed heartbeat, and the console labels it as one.

---

## Simulation behaviour

| Time | Event |
|---|---|
| 0 s | 120 normal ECUs begin publishing valid telemetry |
| ~2 s | LSTM collects 300 baseline samples from normal traffic |
| ~3 s | LSTM trains on collected baseline (background thread) |
| 10 s | 3 attack ECUs injected: `ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER` |
| 10 s+ | Rule violations detected immediately; LSTM drift detected shortly after |

Attack ECU payloads:

| ECU | Payload | Detection method |
|---|---|---|
| `ECU_SPEED` | velocity=180 km/h, accel=−12 m/s² | Rules: `impossible_acceleration`, `acceleration_velocity_mismatch` |
| `ECU_BRAKE` | brake=0.95, velocity=160 km/h, accel=8.5 m/s² | Rules: `impossible_acceleration` + LSTM drift |
| `ECU_STEER` | steering=55°, velocity=100 km/h | Rules: `unsafe_steering_angle` |

---

## The console

Three views share the body of the page, switched from the command bar. The advisory deck stays visible above all three, so the risk gauge and the current narrative never disappear behind a tab.

### Command bar
Identity, the vehicle under observation, the view switcher, feed liveness, LSTM state, a theme toggle, calm mode, and a UTC clock.

The feed indicator reads `/api/summary`'s `last_anomaly`, which is a heartbeat rather than an anomaly time, and ages through **live → stale → down**. The LSTM badge has three states, not two: ready, training, and unavailable — `/api/lstm-status` can return HTTP 500.

### Advisory deck
| Element | Description |
|---|---|
| **Risk gauge** | Weighted vehicle risk, tweened continuously between polls so the number glides rather than stepping |
| **Highest scoring ECUs** | Meters when scores separate. When many ECUs sit at the ceiling together it says how many, then falls back to criticality — which surfaces the safety-critical ECUs out of a two-dozen-way tie |
| **Advisory** | The recommended response from the LSTM advisor, stamped with the time it was written and whether the model was trained at that point. The rest of the advisory string restates the gauge and the chips below it, so it is not repeated |
| **Flagged / Violations** | Ranked ECU chips (cross-ECU findings first) and violation types. Hovering an ECU shows its registry role and criticality |
| **Stats** | ECUs reporting · Anomalous · Open alerts · Last frame |

### Live view
| Panel | Description |
|---|---|
| **Semantic confidence** | Per-ECU confidence over the last 60 s. The ~117 normal ECUs are collapsed into a min/max envelope with a mean line; the highest-scoring anomalous ECUs are drawn individually |
| **Violation rate** | SIEM-style bars, violation count per 10-second bucket |
| **Caught by** | Detector attribution: physics rules, LSTM, both, or unattributed |
| **Alert stream** | Per-ECU alert cards with severity filter and sort. `ACTIVE_ALERTS` is append-only, so filter and sort are load-bearing rather than conveniences. Clicking a card opens the detail drawer |

### Detection view
Every physics rule and cross-ECU consistency check with its trigger threshold, severity, what it protects, its TARA entry and its security goal — plus the open coverage gaps nothing currently catches. Sourced from `frontend/dashboard/reference.py`, which mirrors `checks.py`, `consistency.py`, `docs/Detection.md` and `docs/TARA.md`.

### Evaluation view
The measured figures from `docs/Evaluation.md` §4, each stamped with the script and run that produced it, followed by what those numbers actually say — including that the LSTM contributed no true positives on the standard scenario.

### Themes, motion and standalone views
Light by default, dark via the sun/moon toggle. The `↗` beside the switcher opens the current view on its own — without the deck, in a new browser tab, carrying the current theme — for reading the dense reference tables away from a live incident.

Every animation fires on a data event rather than on hover: a new alert animates in exactly once, severity escalation gets a single pulse, and the feed dot beats only when the timestamp actually advances. **Calm mode** and the OS `prefers-reduced-motion` setting collapse all of it to ~1 ms without changing the layout.

When the backend is unreachable the console says **"No reading"** and holds the last known alerts, rather than showing an all-clear with a risk of 0.0 — losing the data source is not the same as a clean vehicle.

See `frontend/DESIGN_NOTES.md` for the reasoning behind these choices and the API constraints that shaped them.

---

## Extending the project

### Add a new detection rule
Edit `backend/core/checks.py`. Each violation is a dict:
```python
violations.append({"type": "my_rule_name", "severity": "high"})
```

A rule lives in three places, and all three should move together:

1. `backend/core/checks.py` — the check itself.
2. `docs/Detection.md` §2 and §2.1 — the trigger condition and its TARA mapping.
3. `frontend/dashboard/reference.py` — what the console's Detection view shows.

The thresholds in (2) and (3) must be the ones the *code* applies. This has drifted once already: the doc claimed the acceleration mismatch rule fired at 2 m/s² while `checks.py` had always used 4.0 as the tolerance, with 2.0 as a separate floor below which the rule does not apply at all.

### Add a new attack ECU
Append an entry to `ATTACK_ECUS` in `backend/sim/node_attack.py`.

### Change the attack delay
Edit `backend/sim/sim.yaml`:
```yaml
attack_start_after: 10
```

### Tune the LSTM
Edit constants at the top of `backend/ai/advisor.py`:
```python
WINDOW_SIZE   = 20    # timesteps per inference window
TRAIN_STEPS   = 300   # normal samples before first training
RETRAIN_EVERY = 500   # retrain every N steps after initial fit
HIDDEN_DIM    = 32    # LSTM hidden size
NUM_LAYERS    = 2     # LSTM depth
```

### Register an ECU
Edit `backend/core/ecu_registry.py`. `ECU_CRITICALITY` sets the weight (1–5); higher means the ECU contributes more to the vehicle-wide risk score. `ECU_ROLES` sets the human-readable domain the console shows on hover.

**The inventory is currently the honest gap in this project.** `backend/sim/node_normal.py` publishes `ECU_001`–`ECU_120` and none of them are registered, so 120 of the 123 live ECUs fall through to `DEFAULT_WEIGHT = 2` with no domain. The console reports that as "unclassified — registry default" rather than presenting it as a low-criticality finding. An ISO 21434 asset inventory would have to close this gap; see `docs/TARA.md`.

---

## Suggested future improvements

**Detection**
- ~~Cross-ECU correlation (brake + speed + steering consistency)~~ — implemented, `backend/core/consistency.py`
- ~~Replay attack simulation~~ — implemented, `backend/sim/recorder.py` + `replayer.py`
- **Per-ECU LSTM models (currently one shared model)** — now the highest-value item. `docs/Evaluation.md` §4.5 measured the shared model failing to separate a sub-threshold attack from normal traffic, and §4.4 measured it contributing zero true positives on the standard scenario. Also worth fixing alongside: the training buffer in `advisor.py` is a flat list filled by whichever ECU publishes next, so training windows interleave ECUs even though inference windows are correctly per-ECU
- Replay *detection* (valid packets, wrong timing) — design in `docs/Phase3_Plan.md` §2, tracked as TARA-09
- Battery / BMS anomaly rules
- Timing anomaly detection (message frequency spikes)
- Backend throughput: the detection loop processes one message per 50 ms (~20/s) while the simulator publishes ~240/s, so the queue grows unboundedly and injected attacks reach the console minutes late

**Engineering**
- Unit test suite (`pytest`)
- Docker Compose setup
- YAML-driven rule loading (no code changes to add rules)
- Structured logging with `structlog`
- LSTM model persistence (`torch.save` / `torch.load`) so retraining is skipped on restart

**Frontend**
- ~~Severity filter on alerts panel~~ — implemented, with sort order
- ECU heatmap (all 120 ECUs in a grid)
- Historical replay mode
- Analyst case notes / acknowledgment workflow
- Stop rebuilding the alert stream wholesale on every poll: while alerts are arriving every tick, a click on a card can still be lost between the render and its round trip

**Security relevance**
- CAN/CAN-FD frame ingestion (real hardware bridge)
- SOME/IP or automotive Ethernet simulation
- ECU trust score decay over time
- Secure tamper-evident alert log

---

## Tech stack

| Layer | Technology |
|---|---|
| Detection engine | Python, threading |
| LSTM model | PyTorch (CPU, no GPU needed) |
| Message bus | In-process queue (pub/sub) |
| Backend API | Flask |
| Frontend | Dash, Plotly, hand-written CSS (light + dark themes) |
| Config | python-dotenv (optional) |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'backend'`**
Always run scripts from the project root directory (`SemantiCAN/`), not from inside `scripts/` or `backend/`.

```bash
# Correct
cd SemantiCAN
python scripts/run_backend.py

# Wrong
cd SemantiCAN/scripts
python run_backend.py
```

**Dashboard shows no data**
Make sure the backend is running first (`python scripts/run_backend.py`) before starting the dashboard.

**LSTM badge stays in Training state**
The LSTM needs ~300 messages from the 120 normal ECUs. With the default 0.5 s publish interval across 120 ECUs, this takes about 1–2 seconds of wall time. Wait a moment and it will switch to Ready.

**Port already in use**
Kill the previous process or change the port in `backend/api.py` (`start_api(port=5001)`) and `frontend/config.py` (`API_BASE`).

---

## Disclaimer

This is a simulation and prototype project for learning, research, and cybersecurity portfolio demonstration. It is not a production automotive safety controller and should not be used in safety-critical systems.

---

## Author

Built as an automotive cybersecurity / semantic anomaly detection project demonstrating the intersection of:

- Vehicle telemetry analysis
- Physics-based anomaly detection
- On-device LSTM anomaly detection (no cloud dependency)
- SOC tooling and dashboard design
- AI-assisted incident advisory
