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
    checkpoints = [frame.get("native_ai_rng") for frame in rows]
    if any(not isinstance(seed, list) or len(seed) != 2 or
           seed[0] is not None or type(seed[1]) is not int
           for seed in checkpoints):
        raise AssertionError("missing native CPU random checkpoints")
    if len({seed[1] for seed in checkpoints}) < 2:
        raise AssertionError("CPU Park-Miller RNG never advanced")
    memories = [frame.get("native_ai_memory") for frame in rows]
    if any(not isinstance(mem, list) or len(mem) != 2 or
           mem[0] is not None or not isinstance(mem[1], dict) or
           type(mem[1].get("gurt")) is not int or
           not 0 <= mem[1]["gurt"] <= 10 or
           type(mem[1].get("ai_ji")) is not int or
           not 0 <= mem[1]["ai_ji"] <= 65535 or
           type(mem[1].get("aij")) is not int or
           mem[1]["aij"] not in (0, 1)
           for mem in memories):
        raise AssertionError("missing or invalid native AI memory checkpoints")
    # Running/walking/attacking are all real autonomous decisions; having
    # only idle frames is the same disconnected-CPU failure as before.
    if not any(s in stats["state_histogram"] for s in
               ("20", "100", "200", "400", "1100", "1110", "1120")):
        raise AssertionError("unplugged ZSS CPU stayed idle for entire scenario")
    if not stats["observed_attacks"]:
        def fighter(frame: dict, player: int) -> dict:
            return next(c for c in frame["chars"] if
                        c["player_no"] == player and c["helper_index"] == 0)
        def sample(idx: int) -> list[dict]:
            return [
                {key: fighter(rows[idx], p)[key] for key in
                 ("state_no", "pos", "vel", "facing", "ctrl",
                  "state_type", "move_type")}
                for p in (0, 1)
            ]
        diagnostics = {
            "timeline": {str(i): sample(i) for i in
                         (0, 16, 17, 46, 119, len(rows) - 1)},
            "state_histogram": stats["state_histogram"],
            "transitions": stats["state_transitions"][:24],
            "initial": [(fighter(rows[0], p)["state_no"],
                         fighter(rows[0], p)["pos"]) for p in (0, 1)],
            "at_120": [(fighter(rows[119], p)["state_no"],
                        fighter(rows[119], p)["pos"]) for p in (0, 1)],
            "last": [(fighter(rows[-1], p)["state_no"],
                      fighter(rows[-1], p)["pos"]) for p in (0, 1)],
        }
        raise AssertionError("unplugged ZSS CPU never attacked: " +
                             json.dumps(diagnostics, sort_keys=True))
    print("source-informed native ZSS CPU entered active states and attacked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
