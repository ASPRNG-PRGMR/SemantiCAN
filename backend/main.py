"""
Semantic Integrity Domain Controller — main processing loop.

Detection pipeline per message:
  1. Feature extraction (derived acceleration from Δv/Δt)
  2. Physics-based semantic rule checks
  3. LSTM anomaly scoring (trained on first ~300 normal samples)
  4. Score fusion: max(rule_confidence, lstm_confidence)
  5. Alert generation + deduplication
  6. State recording for the API / dashboard
"""

import sys
import time
import json
from pathlib import Path
from threading import Thread

# Ensure project root is importable regardless of working directory
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus          import MessageBus
from backend.sim.node_normal  import start_normal_node
from backend.sim.node_attack  import start_attack_node

from backend.core.features    import FeatureExtractor
from backend.core.checks      import semantic_checks
from backend.core.scoring     import score_violations
from backend.core.alerts      import generate_alert

from backend.ai.advisor       import ingest_message as lstm_ingest

from backend.api              import start_api
from backend.api_state        import record_semantic_state, record_violation

# ── Setup ─────────────────────────────────────────────────────────────────
LOG_DIR        = ROOT / "backend" / "logs"
LOG_DIR.mkdir(exist_ok=True)
ALERT_LOG_FILE = LOG_DIR / "alerts.log"

bus           = MessageBus()
subscription  = bus.subscribe("vehicle_state")
extractor     = FeatureExtractor()

print("[*] Semantic Integrity Domain Controller started")

# ── Start Flask API (background thread) ───────────────────────────────────
Thread(target=start_api, daemon=True).start()
time.sleep(1)
print("[*] Backend API running on http://127.0.0.1:5000")

# ── Start normal ECU simulation ───────────────────────────────────────────
Thread(target=start_normal_node, args=(bus,), daemon=True).start()
print("[*] Normal ECU simulation started (120 ECUs)")
print("[*] LSTM advisor collecting baseline — attacks inject in 10 s ...")


def _delayed_attack():
    time.sleep(10)
    print("[!] Attack ECUs injected (ECU_SPEED, ECU_BRAKE, ECU_STEER)")
    start_attack_node(bus)


Thread(target=_delayed_attack, daemon=True).start()

# ── Main processing loop ──────────────────────────────────────────────────
while True:
    try:
        if not subscription.empty():
            ts, message = subscription.get()
            node_id     = message.get("node_id", "UNKNOWN")

            # 1. Derived features
            features = extractor.extract(ts, message)

            # 2. Physics-based rule violations
            violations              = semantic_checks(message, features)
            rule_severity, rule_conf = score_violations(violations)

            # 3. LSTM anomaly score (0–100)
            lstm_conf = lstm_ingest(message)

            # 4. Fuse scores: take the higher of the two
            fused_conf     = max(rule_conf, lstm_conf)
            fused_severity = rule_severity if rule_conf >= lstm_conf else (
                "critical" if lstm_conf >= 90
                else "high" if lstm_conf >= 75
                else "medium" if lstm_conf >= 60
                else "low"
            )

            # 5. Record ECU state (makes ECU visible on dashboard)
            record_semantic_state(node_id, fused_conf)

            # 6. Generate alert if rule violations OR strong LSTM spike (≥70)
            if violations or lstm_conf >= 70:
                if violations:
                    record_violation()

                alert = generate_alert(
                    node_id    = node_id,
                    violations = violations,
                    severity   = fused_severity,
                    confidence = fused_conf,
                )

                if alert:
                    with open(ALERT_LOG_FILE, "a") as f:
                        f.write(json.dumps(alert) + "\n")

                    print(
                        f"[ALERT] {alert['node_id']} | "
                        f"severity={alert['severity']} | "
                        f"confidence={alert['confidence']:.0f} | "
                        f"lstm={lstm_conf:.0f}"
                    )

        time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[*] Shutting down.")
        break
    except Exception as exc:
        print(f"[ERROR] {exc}")
        time.sleep(0.2)
