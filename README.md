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
│   │   ├── constraints.py    ← Physics helper functions
│   │   ├── ecu_registry.py   ← ECU criticality weights (1–5 scale)
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
│   ├── config.py             ← API base URL, refresh interval, titles
│   │
│   └── dashboard/
│       ├── app.py            ← Dash app entrypoint
│       ├── layout.py         ← Dashboard layout (KPIs, charts, panels)
│       ├── callbacks.py      ← Live Plotly callbacks (pulls from Flask API)
│       └── assets/
│           └── style.css     ← Dark SOC theme (CSS variables)
│
├── scripts/
│   ├── run_backend.py        ← Launch backend (detection + API)
│   ├── run_dashboard.py      ← Launch Dash dashboard
│   └── run_attack.py         ← Manual one-shot attack injection
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
| `GET /api/top-anomalous-ecus` | Top 3 highest-risk ECUs |
| `GET /api/lstm-status` | LSTM training state: `trained` (bool), `samples` collected, `train_steps` run |

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

## Dashboard panels

| Panel | Description |
|---|---|
| **KPI strip** | Active ECUs · Anomalous ECUs · Last anomaly timestamp |
| **LSTM badge** | `◌ Training` → `● Ready` once model is fitted |
| **Confidence history** | Per-ECU confidence over the last 60 seconds. Normal ECUs are collapsed into a single dotted average line; up to 5 anomalous ECUs are shown individually in distinct colours. A `+N more` annotation appears if additional anomalous ECUs are present. |
| **Violation rate** | SIEM-style bar chart: violation count per 10-second bucket with a dynamic y-axis |
| **AI Advisory** | SOC-style narrative generated by the local LSTM advisor, displayed under the charts for visibility |
| **Top anomalous ECUs** | Risk bars for the 3 highest-confidence anomalous ECUs |
| **Active alerts** | Scrollable per-ECU alert cards with severity, confidence, and violation tags |

---

## Extending the project

### Add a new detection rule
Edit `backend/core/checks.py`. Each violation is a dict:
```python
violations.append({"type": "my_rule_name", "severity": "high"})
```

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

### Add ECU criticality weights
Edit `backend/core/ecu_registry.py`. Higher weight (1–5) means the ECU contributes more to the vehicle-wide risk score.

---

## Suggested future improvements

**Detection**
- Cross-ECU correlation (brake + speed + steering consistency)
- Battery / BMS anomaly rules
- Replay attack simulation
- Timing anomaly detection (message frequency spikes)
- Per-ECU LSTM models (currently one shared model)

**Engineering**
- Unit test suite (`pytest`)
- Docker Compose setup
- YAML-driven rule loading (no code changes to add rules)
- Structured logging with `structlog`
- LSTM model persistence (`torch.save` / `torch.load`) so retraining is skipped on restart

**Frontend**
- ECU heatmap (all 120 ECUs in a grid)
- Severity filter on alerts panel
- Historical replay mode
- Analyst case notes / acknowledgment workflow

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
| Frontend | Dash, Plotly, dash-bootstrap-components |
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
