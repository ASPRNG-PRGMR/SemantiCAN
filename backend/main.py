import time
import json
from pathlib import Path
from threading import Thread

from backend.sim.bus import MessageBus
from backend.sim.node_normal import start_normal_node
from backend.sim.node_attack import start_attack_node

from backend.core.features import FeatureExtractor
from backend.core.checks import semantic_checks
from backend.core.scoring import score_violations
from backend.core.alerts import generate_alert

from backend.api import start_api
from backend.api_state import record_semantic_state, record_violation

# ---------------- Setup ----------------

LOG_DIR = Path("backend/logs")
LOG_DIR.mkdir(exist_ok=True)
ALERT_LOG_FILE = LOG_DIR / "alerts.log"

bus = MessageBus()
subscription = bus.subscribe("vehicle_state")
feature_extractor = FeatureExtractor()

print("[*] Semantic Integrity Domain Controller started")

# ---------------- Start API (non-blocking) ----------------

Thread(target=start_api, daemon=True).start()
time.sleep(1)
print("[*] Backend API running on http://127.0.0.1:5000")

# ---------------- Start ECU simulation ----------------

Thread(target=start_normal_node, args=(bus,), daemon=True).start()
print("[*] Normal ECU simulation started (120 ECUs)")


def delayed_attack():
    time.sleep(10)
    print("[!] Attack ECUs injected")
    start_attack_node(bus)


Thread(target=delayed_attack, daemon=True).start()

# ---------------- Main processing loop ----------------

while True:
    try:
        if not subscription.empty():
            ts, message = subscription.get()
            node_id = message.get("node_id", "UNKNOWN")

            features = feature_extractor.extract(ts, message)
            violations = semantic_checks(message, features)
            severity, confidence = score_violations(violations)

            # Record ECU state (this makes ECUs "exist" in the dashboard)
            record_semantic_state(node_id, confidence)

            if violations:
                record_violation()

                alert = generate_alert(
                    node_id=node_id,
                    violations=violations,
                    severity=severity,
                    confidence=confidence,
                )

                if alert:
                    with open(ALERT_LOG_FILE, "a") as f:
                        f.write(json.dumps(alert) + "\n")

                    print(
                        f"[ALERT] {alert['node_id']} | "
                        f"severity={alert['severity']} | "
                        f"confidence={alert['confidence']}"
                    )

        time.sleep(0.05)

    except Exception as e:
        print(f"[ERROR] Runtime exception: {e}")
        time.sleep(0.2)
