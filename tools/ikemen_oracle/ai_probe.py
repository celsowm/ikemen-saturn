#!/usr/bin/env python3
"""Observe autonomous KFM ZSS AI in genuine Ikemen GO (upstream only).

There is no mirrored AI decision engine in the Saturn oracle driver.
This tool measures AI behavior without comparing unlike simulations.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
try:
    from .diff import load_jsonl
except ImportError:
    from diff import load_jsonl


def summarize(rows: list[dict], side: int = 1) -> dict:
    if not rows:
        raise ValueError("no upstream AI frames")
    states: list[int] = []
    attacks = 0
    hit_frames = 0
    for frame_index, frame in enumerate(rows):
        roots = [
            c for c in frame["chars"]
            if c["player_no"] == side and c["helper_index"] == 0
        ]
        if len(roots) != 1:
            raise ValueError(
                f"frame {frame_index}: expected one AI player root, found {len(roots)}"
            )
        root = roots[0]
        states.append(root["state_no"])
        attacks += int(root["move_type"] == 1)
        hit_frames += int(root["move_type"] == 2)
    transitions = [
        {"frame": i, "from": old, "to": cur}
        for i, (old, cur) in enumerate(zip(states, states[1:]), 1)
        if old != cur
    ]
    return {
        "schema": 1,
        "reference": "upstream Ikemen GO only; not Saturn parity",
        "frames": len(rows),
        "ai_player": side + 1,
        "state_histogram": {
            str(number): count for number, count
            in sorted(Counter(states).items())
        },
        "state_transitions": transitions,
        "attack_frames": attacks,
        "hit_reaction_frames": hit_frames,
        "observed_attacks": attacks > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario", type=Path,
        default=ROOT / "tools/ikemen_oracle/ai_scenarios/zss_ai_p2_pressure_360.json",
    )
    parser.add_argument("--ikemen-dir", type=Path, default=ROOT / ".external/Ikemen-GO")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "build/ikemen_oracle/ai_probe",
    )
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    ai_players = [
        i for i in (0, 1)
        if int(scenario.get(f"p{i + 1}_ai", 0)) > 0
    ]
    if len(ai_players) != 1:
        parser.error("upstream AI observation requires exactly one AI player")
    if "kfm_zss/kfm_zss.def" not in scenario[f"p{ai_players[0]+1}"]:
        parser.error("the AI player must be original KFM ZSS")
    args.out.mkdir(parents=True, exist_ok=True)
    trace = args.out / "upstream_ai.jsonl"
    report_path = args.out / "ai_report.json"
    for path in (trace, report_path):
        path.unlink(missing_ok=True)

    proc = subprocess.run([
        sys.executable, str(ROOT / "tools/ikemen_oracle/run.py"),
        str(args.scenario.resolve()),
        "--ikemen-dir", str(args.ikemen_dir.resolve()),
        "--trace", str(trace),
        "--install",
    ], cwd=ROOT, check=False)
    if proc.returncode:
        return proc.returncode

    report = summarize(load_jsonl(trace), ai_players[0])
    if report["frames"] != int(scenario["frames"]):
        raise ValueError("upstream AI trace truncated")
    report["seed"] = scenario["seed"]
    report["ai_level"] = scenario[f"p{ai_players[0]+1}_ai"]
    report["scenario"] = scenario["name"]
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"upstream KFM ZSS AI probe: {report['frames']} frames, "
        f"{len(report['state_transitions'])} transitions, "
        f"{report['attack_frames']} attack frames"
    )
    if not report["observed_attacks"]:
        print("No attack observed. Check AI input-hook routing before making any AI parity claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
