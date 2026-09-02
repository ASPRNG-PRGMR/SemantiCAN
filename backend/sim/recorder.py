"""
TelemetryRecorder — Attack Replay infrastructure, Feature A (Phase3_Plan.md §1).

Subscribes to the Message Bus exactly like the Semantic Integrity Controller
does, as an independent second subscriber (see backend/sim/bus.py for the
fan-out fix that makes this safe). It does not sit in the detection path and
cannot affect detection latency or behaviour.

Two files are written per run, deliberately kept separate (Phase3_Plan.md
§1.8, "current lean is sidecar"):

  telemetry.jsonl     - exactly what was on the bus: {timestamp, node_id, ...}
                         This is the only file the replayer ever reads, so
                         ground truth can never leak into a replayed run.
  ground_truth.jsonl  - {timestamp, node_id, label, scenario}, one line per
                         telemetry line, in the same order, for evaluation
                         scripts to zip up positionally against detector
                         output.

`timestamp` in both files is simulation time (seconds since recording
started), not wall-clock time, per §1.2 — the bus itself only exposes
wall-clock time.time(), so the recorder subtracts its own start time.
"""

import json
import threading
import time
from pathlib import Path

# Attack ECU IDs are hardcoded in node_attack.py rather than exposed as a
# constant, so the mapping is kept here rather than imported. If node_attack.py
# adds a new attack ECU, add it here too.
ATTACK_SCENARIO_BY_NODE = {
    "ECU_SPEED": "spoofed_speed",
    "ECU_BRAKE": "spoofed_brake",
    "ECU_STEER": "spoofed_steer",
}


class TelemetryRecorder:
    def __init__(self, bus, run_dir: Path, topic: str = "vehicle_state"):
        self.bus = bus
        self.topic = topic
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.telemetry_path = self.run_dir / "telemetry.jsonl"
        self.ground_truth_path = self.run_dir / "ground_truth.jsonl"
        self.manifest_path = self.run_dir / "manifest.json"

        self._subscription = bus.subscribe(topic)
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = None
        self._message_count = 0

    def _label_for(self, node_id: str):
        scenario = ATTACK_SCENARIO_BY_NODE.get(node_id)
        if scenario is not None:
            return "attack", scenario
        return "normal", None

    def start(self, attack_delay_seconds: float | None = None):
        """Begin recording. attack_delay_seconds is recorded in the manifest
        only (metadata about the run config), never used to decide labels —
        labels are derived per-message from node_id, which is robust even if
        the attack delay is changed."""
        self._start_time = time.time()

        manifest = {
            "run_dir": str(self.run_dir),
            "topic": self.topic,
            "start_time_wall_clock": self._start_time,
            "attack_delay_seconds_config": attack_delay_seconds,
            "attack_scenarios": ATTACK_SCENARIO_BY_NODE,
            "status": "recording",
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2))

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        with open(self.telemetry_path, "w") as tf, open(self.ground_truth_path, "w") as gf:
            while not self._stop_event.is_set():
                try:
                    wall_ts, message = self._subscription.get(timeout=0.2)
                except Exception:
                    continue

                sim_ts = round(wall_ts - self._start_time, 4)
                node_id = message.get("node_id", "UNKNOWN")
                label, scenario = self._label_for(node_id)

                telemetry_line = {"timestamp": sim_ts, **message}
                ground_truth_line = {
                    "timestamp": sim_ts,
                    "node_id": node_id,
                    "label": label,
                    "scenario": scenario,
                }

                tf.write(json.dumps(telemetry_line) + "\n")
                tf.flush()
                gf.write(json.dumps(ground_truth_line) + "\n")
                gf.flush()
                self._message_count += 1

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

        manifest = json.loads(self.manifest_path.read_text())
        manifest["status"] = "complete"
        manifest["message_count"] = self._message_count
        manifest["duration_seconds"] = round(time.time() - self._start_time, 3)
        self.manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest
