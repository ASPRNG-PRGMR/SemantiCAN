"""
TelemetryReplayer — Attack Replay infrastructure, Feature A (Phase3_Plan.md §1).

Reads telemetry.jsonl written by TelemetryRecorder and republishes each
message to a Message Bus, preserving the original inter-message timing
(scaled by `speed`) so that, from the Semantic Integrity Controller's point
of view, a replayed run looks identical to a live one (Phase3_Plan.md §1.5).

Only ever reads telemetry.jsonl, never ground_truth.jsonl — ground truth is
structurally unreachable from here, which is the whole point of keeping the
two files separate.
"""

import json
import time
from pathlib import Path


class TelemetryReplayer:
    def __init__(self, bus, telemetry_path: Path, topic: str = "vehicle_state", speed: float = 1.0):
        self.bus = bus
        self.telemetry_path = Path(telemetry_path)
        self.topic = topic
        self.speed = speed  # 0 or None => publish as fast as possible, no pacing
        self.published_count = 0

    def _iter_lines(self):
        with open(self.telemetry_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def run(self):
        """Blocking replay of the entire recording onto the bus."""
        prev_sim_ts = None
        for record in self._iter_lines():
            sim_ts = record.pop("timestamp")

            if self.speed and prev_sim_ts is not None:
                gap = (sim_ts - prev_sim_ts) / self.speed
                if gap > 0:
                    time.sleep(gap)

            # `record` is now exactly the original message dict (node_id + payload)
            self.bus.publish(self.topic, record)
            self.published_count += 1
            prev_sim_ts = sim_ts

        return self.published_count
