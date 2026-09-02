"""
CLI: record a live simulation run to disk.

Usage (from project root):
    python -m backend.sim.record --output backend/recordings/run_001 --duration 30

Spins up its own MessageBus, normal ECU node, and (after the configured
delay) attack ECU node — mirroring backend/main.py's setup — with a
TelemetryRecorder attached as a second subscriber. Does not start the
detection pipeline or the Flask API; this is recording only.
"""

import argparse
import sys
import time
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus import MessageBus
from backend.sim.node_normal import start_normal_node
from backend.sim.node_attack import start_attack_node
from backend.sim.recorder import TelemetryRecorder


def main():
    parser = argparse.ArgumentParser(description="Record a SemantiCAN telemetry run")
    parser.add_argument("--output", required=True, help="Output run directory")
    parser.add_argument("--duration", type=float, default=30.0, help="Recording length in seconds")
    parser.add_argument("--attack-delay", type=float, default=10.0, help="Seconds before attack ECUs inject")
    args = parser.parse_args()

    bus = MessageBus()
    recorder = TelemetryRecorder(bus, Path(args.output))

    # Recorder must start listening (and stamp start_time) before any
    # publisher starts, or the first batch of messages can arrive with a
    # negative simulation-time offset.
    recorder.start(attack_delay_seconds=args.attack_delay)
    print(f"[*] Recording to {recorder.run_dir}/ for {args.duration}s ...")

    Thread(target=start_normal_node, args=(bus,), daemon=True).start()
    print(f"[*] Normal ECU simulation started (120 ECUs)")

    def _delayed_attack():
        time.sleep(args.attack_delay)
        print(f"[!] Attack ECUs injected (ECU_SPEED, ECU_BRAKE, ECU_STEER)")
        start_attack_node(bus)

    Thread(target=_delayed_attack, daemon=True).start()

    time.sleep(args.duration)

    manifest = recorder.stop()
    print(f"[*] Recording complete: {manifest['message_count']} messages, "
          f"{manifest['duration_seconds']}s")
    print(f"    telemetry:    {recorder.telemetry_path}")
    print(f"    ground_truth: {recorder.ground_truth_path}")
    print(f"    manifest:     {recorder.manifest_path}")


if __name__ == "__main__":
    main()
