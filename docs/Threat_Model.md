# Threat Model - SemantiCAN

**Status:** Draft v0.1 - initial pass, to be refined in Phase 2 Step 2 (TARA) and Phase 2 Step 3 (ISO 21434 rule mapping).

## 1. Purpose

This document describes the threat model for SemantiCAN, an EV semantic integrity monitor that detects physically and semantically inconsistent ECU telemetry using physics-based rules and a locally-trained LSTM model. It defines what the system protects, who might attack it, what assumptions the system relies on, and what security goals the detection layer is trying to satisfy.

This is an engineering document, not an implementation description - no code is referenced here beyond what is necessary to describe a boundary or an asset.

---

## 2. Assets

Assets are the things in the system that have value and whose compromise would cause harm - either directly (vehicle safety) or indirectly (operator trust, data integrity).

| Asset | Description | Why it matters |
|---|---|---|
| **Telemetry integrity** | The correctness of velocity, acceleration, steering angle, and brake values as reported by each ECU | Downstream safety and monitoring decisions depend on these values being truthful |
| **ECU trustworthiness** | The assumption that a given ECU is the legitimate source of the messages attributed to it | A spoofed or compromised ECU can inject false telemetry without triggering a network-layer alert |
| **Detection pipeline integrity** | The correctness of the Semantic Integrity Controller's rule engine and LSTM scoring | If the detector itself can be fooled or starved, all downstream protections fail silently |
| **Vehicle risk score** | The criticality-weighted, aggregated risk value exposed to the dashboard/API | Operators and (in a real deployment) safety systems may act on this score |
| **Alert store / log** | The record of generated alerts (`backend/logs/alerts.log`, in-memory alert store) | Needed for incident response, forensics, and demonstrating detection worked |
| **SOC Dashboard / API** | The Flask API and Dash dashboard that expose system state | If compromised or spoofed, an operator could be shown a false "all clear" |
| **LSTM baseline / training data** | The rolling sample store used to train the anomaly model | If poisoned, the model's definition of "normal" becomes attacker-controlled |

---

## 3. Attack Surface

Where an adversary could realistically interact with or influence the system.

| Surface | Description |
|---|---|
| **Vehicle network / message bus** | The channel over which ECU telemetry is published. In the current simulation this is an in-process pub/sub bus; in a real vehicle this maps to CAN / CAN-FD / automotive Ethernet |
| **Individual ECUs** | Any ECU (`ECU_SPEED`, `ECU_BRAKE`, `ECU_STEER`, or one of the 120 simulated normal ECUs) is a potential injection point if compromised |
| **Baseline / training window** | The first ~300 samples used to train the LSTM - an attacker present during this window could bias the learned "normal" distribution |
| **Backend API** | `/api/summary`, `/api/alerts`, `/api/semantic-history`, `/api/violation-rate`, `/api/top-anomalous-ecus`, `/api/lstm-status` - currently unauthenticated HTTP endpoints |
| **Dashboard client** | The Dash frontend, which trusts and renders whatever the backend API returns |
| **Configuration surface** | `backend/sim/sim.yaml`, `backend/core/ecu_registry.py`, and LSTM constants in `backend/ai/advisor.py` - not attacker-reachable in the current simulation, but relevant if the system were deployed with remote config |

---

## 4. Threat Actors

| Actor | Capability | Motivation |
|---|---|---|
| **Compromised ECU (malicious firmware)** | Can send arbitrary but protocol-valid telemetry values as if they were legitimate | Cause unsafe vehicle behavior, mask a real fault, or evade detection |
| **On-bus attacker (physical or remote access to the vehicle network)** | Can inject or replay messages, potentially impersonating a legitimate ECU ID | Denial of safety, sensor spoofing, reconnaissance |
| **Insider / supply-chain actor** | Can influence an ECU during manufacturing or update, or tamper with the training/baseline data pipeline | Long-horizon, harder-to-detect manipulation (e.g., poisoning what the LSTM learns as "normal") |
| **Dashboard/API consumer (network-adjacent attacker)** | Can query or attempt to manipulate the unauthenticated API | Information disclosure, false-negative reporting to an operator |

This is a bench-level threat model for a research/portfolio prototype, not a production TARA - actor capability is described qualitatively, not scored yet. Formal likelihood/impact scoring happens in the TARA (Phase 2 Step 2).

---

## 5. Attack Assumptions

Assumptions the system currently makes, stated explicitly so they can be challenged:

- The message bus itself is assumed reliable and available (no bus-level denial-of-service modeling yet).
- ECU identity (the `ECU_ID` field) is trusted at face value - there is no cryptographic authentication of message origin in the current prototype.
- The first ~300 samples collected for LSTM training are assumed to be attack-free ("clean baseline" assumption). This is a known weak point (see Section 6, Trust Boundaries).
- The rule engine's thresholds (e.g., >140 km/h with <1 m/s² accel, >7 m/s² absolute acceleration, >30° steering above 80 km/h) are assumed to represent genuine physical impossibility or unsafe combinations for the vehicle class being modeled.
- The backend API and dashboard are assumed to run on a trusted local network in the current prototype; no authentication, TLS, or rate-limiting is modeled yet.

---

## 6. Security Goals

What the system is trying to guarantee, independent of implementation:

1. **Telemetry integrity monitoring** - detect, with acceptable delay, when reported telemetry is physically inconsistent or statistically anomalous relative to learned normal behavior.
2. **Timely alerting** - surface high-confidence anomalies to the SOC dashboard with enough context (violated rule, confidence score, affected ECU) to support operator triage.
3. **Resilience to single-vector evasion** - an attacker able to defeat one detection method (rules) should not automatically defeat the other (LSTM), and vice versa. This motivates the current `max(rule_confidence, lstm_confidence)` fusion.
4. **Explainability** - every alert should be traceable to a specific violated rule or a specific anomalous score, not an opaque black-box judgment.
5. **Auditability** - every alert should be logged in a way that supports later forensic review.

Non-goals (explicitly out of scope for this prototype): real-time safety intervention (e.g., actuator lockout), cryptographic message authentication, and production-grade key management. These may become future work items (see `Future_Work.md`).

---

## 7. Trust Boundaries

| Boundary | Trusted side | Untrusted / lower-trust side |
|---|---|---|
| **ECU ↔ Message Bus** | The bus itself and the controller consuming it | Every publishing ECU - normal or attack - is treated as potentially adversarial input |
| **Message Bus ↔ Semantic Integrity Controller** | The controller's internal logic | Raw telemetry values arriving on the bus |
| **LSTM training window ↔ inference** | The trained model, once fitted | The baseline data used to fit it - this boundary is currently weak, since the baseline is assumed clean rather than verified clean |
| **Detection pipeline ↔ Backend API** | The Flask API process | Nothing external is assumed to write into this boundary today, but this is the natural point where authentication would be added |
| **Backend API ↔ Dashboard** | Neither side currently authenticates the other | This is flagged as a gap; a real SOC deployment would require the dashboard to authenticate to the API |
| **Backend API ↔ external consumer** | N/A | Any client able to reach the Flask port can currently read alert data - no authorization boundary exists yet |

---

## 8. Open Questions / Next Steps

- ~~Formalize each entry above into a TARA~~ - done, see `TARA.md` (TARA-01 through TARA-08).
- ~~Map each existing and planned detection rule to a specific threat and security goal~~ - done, see `Detection.md` §2.1.
- Decide whether ECU identity spoofing is in-scope for this prototype, since the current detection layer only reasons about telemetry values, not message provenance (open - tracked as TARA-08).
- Decide which unmitigated TARA entries (TARA-05, TARA-06, TARA-07, TARA-08) to prioritize in Phase 3, given the roadmap caps Phase 3 at one or two technical improvements.
