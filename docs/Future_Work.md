# Future Work - SemantiCAN

**Status:** Draft v0.1 - consolidated from the README's "Suggested future improvements" and the project roadmap. This is a living list; items move to "In Progress" / "Done" as phases are executed.

## 1. Detection

- **Cross-ECU correlation** - brake + speed + steering consistency, instead of independent per-ECU rules. (Roadmap Phase 3 candidate.)
- **Battery / BMS anomaly rules** - extend physics rules beyond velocity/acceleration/steering.
- **Replay attack simulation** - valid packets, wrong timing. (Roadmap Phase 3 candidate.)
- **Timing anomaly detection** - message frequency spikes / gaps.
- **Per-ECU LSTM models** - currently one shared model across all ECUs; per-ECU models would be more representative of real heterogeneous ECU behavior.
- **Trust Score** - decaying per-ECU trust value (e.g., `100 → 98 → 95 → 80`) instead of binary Normal/Alert. (Roadmap Phase 3 candidate.)
- **Vehicle Health Score** - aggregate integrity percentage (e.g., `92% → 71% → 38%`) instead of raw alert count. (Roadmap Phase 3 candidate.)

## 2. Engineering

- **Unit test suite** (`pytest`) - no automated tests currently exist.
- **Docker Compose setup** - for reproducible local deployment of backend + dashboard together.
- **YAML-driven rule loading** - add/modify detection rules without code changes.
- **Structured logging** (`structlog`) - replace ad hoc logging with structured, queryable logs.
- **LSTM model persistence** (`torch.save` / `torch.load`) - skip retraining on every restart.

## 3. Frontend

- **ECU heatmap** - visualize all 120 ECUs in a grid rather than only the top anomalous ones.
- **Severity filter** on the alerts panel.
- **Historical replay mode** - step through a past run in the dashboard.
- **Analyst case notes / acknowledgment workflow** - closer to real SOC tooling.

## 4. Security Relevance

- **CAN / CAN-FD frame ingestion** - real hardware bridge, moving beyond the in-process simulation.
- **SOME/IP or automotive Ethernet simulation.**
- **ECU trust score decay over time** (related to the Detection section's Trust Score item, but framed as a security control rather than just a UX improvement).
- **Secure, tamper-evident alert log** - addresses the "Alert Store / log" asset and the Auditability security goal in `Threat_Model.md`.
- **Authentication between dashboard and backend API** - closes the trust-boundary gap noted in `Architecture.md` §6.
- **Cryptographic ECU message authentication** - addresses the "ECU identity is trusted at face value" assumption in `Threat_Model.md` §5.
- **Baseline-poisoning defenses for the LSTM** - some mechanism to detect or resist a compromised training window (`Threat_Model.md` §5–6).

## 5. Roadmap-Level Future Work (post-technical-improvements)

These come from the broader project roadmap, not the README, and are noted here for continuity:

- Full TARA covering every threat identified in `Threat_Model.md`.
- ISO 21434 mapping for every detection rule (`Detection.md` §2.1).
- Formal evaluation results (`Evaluation.md`).
- Technical paper: *"Semantic Integrity Monitoring for Automotive ECU Telemetry"*.

## 6. Explicit Non-Goals (for now)

Kept here so scope decisions are visible, not just implicit:

- Real-time safety intervention (e.g., actuator lockout) - out of scope; this is a monitoring/detection system, not a safety controller (see the project's disclaimer).
- Production-grade key management - out of scope until/unless the project moves toward real hardware integration.
