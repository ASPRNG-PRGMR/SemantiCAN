# EV Semantic Integrity Monitor

### Automotive Cybersecurity · Vehicle Telemetry Anomaly Detection · SOC Dashboard

An automotive cybersecurity simulation platform that detects **semantic anomalies in ECU telemetry** and visualizes them through a live SOC-style dashboard.

This project demonstrates how a vehicle can be monitored not just for malformed packets or protocol abuse, but for **physically inconsistent or suspicious telemetry values** that may indicate compromised ECUs, spoofed telemetry, or semantic data injection attacks.

---

## Why this matters

Most IDS solutions in automotive networks focus on CAN IDs, packet signatures, malformed frames, or unusual traffic patterns. But a sophisticated attacker may still send **perfectly valid-looking messages** carrying **unsafe or physically impossible values**.

**Example:**
- Vehicle reports **180 km/h**
- While also reporting **−12 m/s² acceleration**
- Or a steering angle that is unsafe for the current speed

These messages are syntactically valid — but **semantically suspicious**.

This project focuses on detecting exactly that layer.

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
                   +----------------------+
                   | Semantic Integrity   |
                   | Domain Controller   |
                   |----------------------|
                   | Feature Extraction   |
                   | Semantic Checks      |
                   | Violation Scoring    |
                   | Alert Generation     |
                   +----------+-----------+
                              |
              +---------------+------------------+
              |                                  |
              v                                  v
    +----------------------+        +---------------------------+
    | Vehicle Risk Engine  |        | Flask Backend API         |
    | AI Advisory Layer    |        |---------------------------|
    | Alert Store          |        | /api/summary              |
    +----------------------+        | /api/alerts               |
                                    | /api/semantic-history     |
                                    | /api/violation-rate       |
                                    | /api/top-anomalous-ecus   |
                                    +-------------+-------------+
                                                  |
                                                  v
                                    +---------------------------+
                                    |   Dash SOC Dashboard      |
                                    +---------------------------+
```

---

## Features

### Backend detection engine
- Physics-based semantic validation rules
- Derived feature extraction (e.g. acceleration inferred from Δvelocity/Δtime)
- Cross-check: reported acceleration vs. derived acceleration
- Confidence scoring per violation severity
- Per-ECU alert deduplication
- ECU-criticality-weighted vehicle risk score
- Rolling anomaly history and violation-rate tracking

### Anomaly scenarios detected
| Rule | Severity |
|---|---|
| Velocity > 140 km/h without corresponding acceleration | HIGH |
| Absolute acceleration > 7 m/s² (physically impossible for road vehicles) | CRITICAL |
| Steering angle > 30° at speeds > 80 km/h | MEDIUM |
| Reported acceleration vs. derived acceleration mismatch > 2 m/s² | HIGH |

### SOC Dashboard
- Live KPI cards: active ECUs, anomalous ECUs, last anomaly time
- Semantic confidence history chart (per ECU, colour-coded)
- Violation rate chart (SIEM-style time buckets)
- Top anomalous ECUs with risk bars
- Active alerts panel with violation tags
- AI advisory panel (LLM-generated SOC narrative, or deterministic fallback)

### AI Advisory
Uses **NVIDIA NIM** (`llama-3.1-70b-instruct`) to generate analyst-grade explanations of active anomalies. Falls back to a deterministic template when no API key is configured, so **the system works fully offline**.

---

## Project structure

```
SemantiCAN/
│
├── backend/
│   ├── main.py               ← Orchestration: simulation + detection loop
│   ├── api.py                ← Flask API
│   ├── api_state.py          ← In-memory rolling state store
│   │
│   ├── ai/
│   │   └── advisor.py        ← NVIDIA NIM advisory (with fallback)
│   │
│   ├── core/
│   │   ├── alerts.py         ← Alert generation and deduplication
│   │   ├── checks.py         ← Semantic validation rules
│   │   ├── constraints.py    ← Physics helper functions
│   │   ├── ecu_registry.py   ← ECU criticality weights
│   │   ├── features.py       ← Feature extraction (derived acceleration)
│   │   ├── scoring.py        ← Violation → severity + confidence
│   │   └── vehicle_risk.py   ← Weighted vehicle risk score
│   │
│   ├── sim/
│   │   ├── bus.py            ← In-memory pub/sub message bus
│   │   ├── ecu_ids.py        ← 120 ECU IDs + malicious set
│   │   ├── node_normal.py    ← Normal ECU telemetry publisher
│   │   ├── node_attack.py    ← Attack ECU injector
│   │   └── sim.yaml          ← Simulation config
│   │
│   ├── security/
│   │   └── env.py            ← Safe .env loader
│   │
│   └── logs/
│       └── alerts.log        ← Persisted alert log (auto-created)
│
├── frontend/
│   ├── config.py             ← API URLs, refresh interval, titles
│   │
│   └── dashboard/
│       ├── app.py            ← Dash app entrypoint
│       ├── layout.py         ← Dashboard layout
│       ├── callbacks.py      ← Live data callbacks
│       └── assets/
│           └── style.css     ← Dark SOC theme
│
├── scripts/
│   ├── run_backend.py        ← Convenience launcher: backend
│   ├── run_dashboard.py      ← Convenience launcher: dashboard
│   └── run_attack.py        ← Manual attack injection
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Quick start

### 1. Clone

```bash
Clone the repository - git clone https://github.com/ASPRNG-PRGMR/EdgeRover
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

### 4. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env and add your NVIDIA_API_KEY if you have one.
# The system works fully without it — AI advisory uses a fallback response.
```

### 5. Run the backend

```bash
python scripts/run_backend.py
```

You should see:

```
[*] Semantic Integrity Domain Controller started
[*] Backend API running on http://127.0.0.1:5000
[*] Normal ECU simulation started (120 ECUs)
... (after 10 seconds) ...
[!] Attack ECUs injected
[ALERT] ECU_SPEED | severity=critical | confidence=90
```

### 6. Run the dashboard

In a second terminal (with the venv activated):

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
| `GET /api/alerts` | All active alerts with violations, severity, AI analysis |
| `GET /api/top-anomalous-ecus` | Top 3 highest-risk ECUs |

---

## Simulation behaviour

| Time | Event |
|---|---|
| 0 s | 120 normal ECUs begin publishing valid telemetry |
| 10 s | 3 attack ECUs injected: `ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER` |
| 10 s+ | Semantic violations detected, alerts generated, dashboard updates |

Attack ECU payloads:
- **ECU_SPEED** — velocity 180 km/h + acceleration −12 m/s² (impossible)
- **ECU_BRAKE** — brake pressure 0.95 + velocity 120 km/h (brake/speed mismatch)
- **ECU_STEER** — steering angle 45° at 80 km/h (unsafe cornering)

---

## Extending the project

### Add a new detection rule
Edit `backend/core/checks.py` and append a new block to `semantic_checks()`. Each violation is a dict with `type` and `severity` (`critical` / `high` / `medium` / `low`).

### Add a new attack ECU
Append an entry to the `ATTACK_ECUS` list in `backend/sim/node_attack.py`.

### Change the attack delay
Edit `backend/sim/sim.yaml`:
```yaml
attack_start_after: 10   # seconds
```
Then in `backend/main.py`, read this value with PyYAML instead of the hardcoded `time.sleep(10)`.

### Add ECU criticality weights
Edit `backend/core/ecu_registry.py`. Higher weight (1–5) means the ECU contributes more to the vehicle-wide risk score.

---

## Suggested future improvements

**Detection**
- Cross-ECU correlation (e.g. brake + speed + steering consistency)
- Battery / BMS anomaly rules
- Replay attack simulation
- Timing anomaly detection (message frequency spikes)

**Engineering**
- Unit test suite (`pytest`)
- Docker Compose setup
- YAML-driven rule loading (no code changes to add rules)
- Structured logging with `structlog`

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
| Message bus | In-process queue (pub/sub) |
| Backend API | Flask |
| Frontend | Dash, Plotly, dash-bootstrap-components |
| AI advisory | NVIDIA NIM (llama-3.1-70b-instruct) |
| Config | python-dotenv |

---

## Disclaimer

This is a **simulation and prototype project** for learning, research, and cybersecurity portfolio demonstration. It is not a production automotive safety controller and should not be used in safety-critical systems.

---

## Author

Built as an automotive cybersecurity / semantic anomaly detection project demonstrating the intersection of:

- Vehicle telemetry analysis
- Physics-based anomaly detection
- SOC tooling and dashboard design
- AI-assisted incident advisory
