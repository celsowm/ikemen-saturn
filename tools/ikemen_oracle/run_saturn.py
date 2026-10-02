#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from .inputs import setup_string, write_timeline
except ImportError:
    from inputs import setup_string, write_timeline

ROOT = Path(__file__).resolve().parents[2]

# The Saturn side of the oracle is the host build of the same sources the
# console runs (CMake target ikemen_oracle_trace in the host configuration):
# one source list, compiled by CMake with the generated KFM assets.
DEFAULT_TRACE_BIN = ROOT / "build" / "host" / (
    "ikemen_oracle_trace.exe" if sys.platform == "win32"
    else "ikemen_oracle_trace")

def load_scenario(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("frames", 0)) <= 0:
        raise SystemExit("scenario.frames must be > 0")
    return data

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("build/ikemen_oracle/libsaturn.jsonl"),
    )
    parser.add_argument(
        "--trace-bin",
        type=Path,
        default=Path(os.environ.get("IKEMEN_TRACE_BIN", DEFAULT_TRACE_BIN)),
        help="host-built ikemen_oracle_trace executable "
             "(cmake --preset host && cmake --build --preset host)",
    )
    args = parser.parse_args()

    scenario = load_scenario(args.scenario)
    frames = int(scenario["frames"])
    seed = int(scenario.get("seed", 1))
    trace = args.trace.resolve()
    trace.parent.mkdir(parents=True, exist_ok=True)
    host_bin = args.trace_bin.resolve()
    if not host_bin.is_file():
        raise SystemExit(
            f"{host_bin} not found: build the host configuration first "
            "(cmake --preset host && cmake --build --preset host)")
    timeline = trace.parent / "inputs.txt"
    write_timeline(timeline, scenario)

    run_cmd = [
        str(host_bin), str(trace), str(frames), str(seed), str(timeline),
        setup_string(scenario),
    ]
    subprocess.run(run_cmd, cwd=ROOT, check=True)

    count = 0
    with trace.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    if count != frames:
        raise SystemExit(
            f"Saturn trace has {count} frames, expected {frames}"
        )
    print(f"saturn trace: {trace} ({count} frames)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
