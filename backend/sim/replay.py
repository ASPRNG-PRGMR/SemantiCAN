"""
CLI: replay a recorded run onto a fresh Message Bus.

Usage (from project root):
    python -m backend.sim.replay --input backend/recordings/run_001 --speed 1.0
    python -m backend.sim.replay --input backend/recordings/run_001 --speed 10.0

Standalone, this just republishes telemetry and reports a count — useful for
sanity-checking a recording. For actually running the recording through the
detection pipeline and scoring it against ground truth, see
scripts/evaluate_replay.py, which uses TelemetryReplayer directly rather
than this CLI wrapper.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.sim.bus import MessageBus
from backend.sim.replayer import TelemetryReplayer


def main():
    parser = argparse.ArgumentParser(description="Replay a SemantiCAN telemetry recording")
    parser.add_argument("--input", required=True, help="Run directory containing telemetry.jsonl")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (0 = as fast as possible)")
    args = parser.parse_args()

    telemetry_path = Path(args.input) / "telemetry.jsonl"
    bus = MessageBus()
    replayer = TelemetryReplayer(bus, telemetry_path, speed=args.speed)

    print(f"[*] Replaying {telemetry_path} at speed={args.speed} ...")
    count = replayer.run()
    print(f"[*] Replay complete: {count} messages published to bus (no subscriber attached in this CLI mode)")


if __name__ == "__main__":
    main()
