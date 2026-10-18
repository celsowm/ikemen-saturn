#!/usr/bin/env python3
"""CI smoke for genuinely enabled, bounded CPU in the Saturn trace executable.

This test makes NO comparison to upstream Ikemen AI decisions: it only checks
the CLI-to-frame-driver route and the non-vacuous autonomous combat activity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

try:
    from .diff import load_jsonl
    from .run_saturn import ROOT
    from .ai_probe import summarize
except ImportError:
    from diff import load_jsonl
    from run_saturn import ROOT
    from ai_probe import summarize


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-bin", type=Path, required=True)
    parser.add_argument(
        "--scenario", type=Path,
        default=ROOT / "tools/ikemen_oracle/ai_scenarios/zss_ai_p2_pressure_360.json"
    )
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    trace = ROOT / "build/ikemen_oracle/native_ai_smoke/trace.jsonl"
    subprocess.run([
        sys.executable, str(ROOT / "tools/ikemen_oracle/run_saturn.py"),
        str(args.scenario.resolve()), "--trace", str(trace),
        "--trace-bin", str(args.trace_bin.resolve()),
    ], cwd=ROOT, check=True)
    rows = load_jsonl(trace)
    if len(rows) != int(scenario["frames"]):
        raise AssertionError("native AI frame count mismatch")
    stats = summarize(rows, 1)
    # Running/walking/attacking are all real autonomous decisions; having
    # only idle frames is the same disconnected-CPU failure as before.
    if not any(s in stats["state_histogram"] for s in
               ("20", "100", "200", "400", "1100", "1110", "1120")):
        raise AssertionError("unplugged ZSS CPU stayed idle for entire scenario")
    if not stats["observed_attacks"]:
        raise AssertionError("unplugged ZSS CPU never attacked")
    print("source-informed native ZSS CPU entered active states and attacked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
