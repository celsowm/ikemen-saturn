#!/usr/bin/env python3
"""Compare two real autonomous CPU traces, without claiming Ikemen AI parity.

The original GO RNG/evaluation order and the Saturn local LCG differ, so the
point here is measurable divergence and first-state diagnosis, not a strict
match gate or an artificial alignment of one player's decisions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

try:
    from .ai_probe import summarize
    from .diff import load_jsonl
    from .run_saturn import cpu_levels
    from .rng_audit import audit_checkpoints, compare_draws
    from .rng_events import load_and_audit
except ImportError:
    from ai_probe import summarize
    from diff import load_jsonl
    from run_saturn import cpu_levels
    from rng_audit import audit_checkpoints, compare_draws
    from rng_events import load_and_audit

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO = (
    ROOT / "tools/ikemen_oracle/ai_scenarios/zss_ai_p2_pressure_360.json"
)


def root(row: dict, player: int) -> dict:
    roots = [c for c in row["chars"] if
             c.get("player_no") == player and c.get("helper_index") == 0]
    if len(roots) != 1:
        raise ValueError(f"expected one root for player {player}, got {len(roots)}")
    return roots[0]


def compare_ai(upstream: list[dict], saturn: list[dict], player: int) -> dict:
    if len(upstream) != len(saturn) or not upstream:
        raise ValueError(
            f"AI trace lengths differ: upstream={len(upstream)}, "
            f"Saturn={len(saturn)}"
        )
    u = summarize(upstream, player)
    s = summarize(saturn, player)
    mismatch = []
    states_equal = 0
    for i, (original, native) in enumerate(zip(upstream, saturn)):
        if original.get("frame") != native.get("frame"):
            raise ValueError(f"trace frame indices differ at row {i}")
        x, y = root(original, player), root(native, player)
        if x["state_no"] == y["state_no"]:
            states_equal += 1
        else:
            mismatch.append({
                "frame": i,
                "upstream_state": x["state_no"],
                "saturn_state": y["state_no"],
                "upstream_state_time": x["state_time"],
                "saturn_state_time": y["state_time"],
            })
    checkpoints = [frame.get("native_ai_rng") for frame in saturn]
    if any(value is not None for value in checkpoints):
        if any(not isinstance(value, list) or len(value) != 2 or
               type(value[player]) is not int for value in checkpoints):
            raise ValueError("per-frame native AI RNG checkpoints missing")
    rng_first = checkpoints[0][player] if checkpoints[0] else None
    rng_last = checkpoints[-1][player] if checkpoints[-1] else None

    # The original global RNG and native-local RNG have different owners.
    # Derive call counts from consecutive post-frame seeds, never align the
    # raw seed values or pretend an equal draw count means decision parity.
    upstream_seeds = [frame.get("rand_seed") for frame in upstream]
    upstream_rng = None
    native_rng = None
    if all(seed is not None for seed in upstream_seeds):
        upstream_rng = audit_checkpoints(upstream_seeds)
    elif any(seed is not None for seed in upstream_seeds):
        raise ValueError("partial upstream global RNG checkpoints")
    if all(value is not None for value in checkpoints):
        native_rng = audit_checkpoints([value[player] for value in checkpoints])
    rng_draw_comparison = compare_draws(upstream_rng, native_rng)
    return {
        "schema": 1,
        "comparison": "diagnostic only; not AI RNG or frame parity",
        "frames": len(upstream),
        "ai_player": player + 1,
        "state_equal_frames": states_equal,
        "state_mismatch_frames": len(mismatch),
        "first_state_mismatch": mismatch[0] if mismatch else None,
        "first_10_mismatches": mismatch[:10],
        "upstream": u,
        "saturn": s,
        "upstream_attack_frames": u["attack_frames"],
        "saturn_attack_frames": s["attack_frames"],
        "upstream_transitions": len(u["state_transitions"]),
        "saturn_transitions": len(s["state_transitions"]),
        "observed_attacks_on_both_sides":
            u["observed_attacks"] and s["observed_attacks"],
        "ai_parity_verified": False,
        "random_debug": {
            "upstream_global_first": upstream[0].get("rand_seed"),
            "upstream_global_last": upstream[-1].get("rand_seed"),
            "native_cpu_first": rng_first,
            "native_cpu_last": rng_last,
            "same_random_stream": False,
            "upstream_global_draw_audit": upstream_rng,
            "native_cpu_draw_audit": native_rng,
            "draw_count_comparison": rng_draw_comparison,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--ikemen-dir", type=Path, default=ROOT / ".external/Ikemen-GO")
    parser.add_argument("--trace-bin", type=Path, default=None)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "build/ikemen_oracle/ai_comparison")
    parser.add_argument("--rng-events", action="store_true",
                        help="capture attributed GO Random() calls (opt-in)")
    parser.add_argument("--reuse-traces", action="store_true",
                        help="compare existing traces, do not launch either engine")
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    levels = cpu_levels(scenario)
    players = [i for i, level in enumerate(levels) if level]
    if len(players) != 1:
        parser.error("exactly one KFM ZSS CPU player is required")
    args.out.mkdir(parents=True, exist_ok=True)
    up_path = args.out / "upstream_ai.jsonl"
    sat_path = args.out / "saturn_ai.jsonl"
    events_path = args.out / "upstream_rng_events.jsonl"
    if not args.reuse_traces:
        for file in (up_path, sat_path, events_path):
            file.unlink(missing_ok=True)
        upstream_command = [
            sys.executable, str(ROOT / "tools/ikemen_oracle/run.py"),
            str(args.scenario.resolve()), "--ikemen-dir",
            str(args.ikemen_dir.resolve()), "--trace", str(up_path),
            "--install",
        ]
        if args.rng_events:
            upstream_command += ["--rng-events", str(events_path)]
        sat_command = [
            sys.executable, str(ROOT / "tools/ikemen_oracle/run_saturn.py"),
            str(args.scenario.resolve()), "--trace", str(sat_path),
        ]
        if args.trace_bin:
            sat_command += ["--trace-bin", str(args.trace_bin.resolve())]
        for cmd in (upstream_command, sat_command):
            result = subprocess.run(cmd, cwd=ROOT, check=False)
            if result.returncode:
                return result.returncode
    if not up_path.is_file() or not sat_path.is_file():
        parser.error("both existing upstream_ai.jsonl and saturn_ai.jsonl required")

    expected = int(scenario["frames"])
    original = load_jsonl(up_path)
    native = load_jsonl(sat_path)
    if len(original) != expected or len(native) != expected:
        raise ValueError("AI trace is missing frames from this scenario")
    report = compare_ai(original, native, players[0])
    report.update({"scenario": scenario["name"], "seed": scenario["seed"],
                   "ai_level": levels[players[0]]})
    if args.rng_events:
        report["upstream_rng_events"] = load_and_audit(original, events_path)
    outfile = args.out / "comparison.json"
    outfile.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"CPU diagnostic: {report['state_equal_frames']}/{expected} "
        "matching state numbers; "
        f"{report['upstream_attack_frames']}/{report['saturn_attack_frames']} "
        "upstream/native attack frames; NOT full AI parity."
    )
    print(f"report: {outfile}")
    if args.rng_events:
        events = report["upstream_rng_events"]
        print(f"Upstream original Random(): {events['event_count']} "
              f"attributed calls, {events['verified_intervals']} "
              "checkpoint intervals reconciled")
    draws = report["random_debug"]["draw_count_comparison"]
    if draws["available"]:
        print("Park-Miller RNG diagnostic: "
              f"{draws['different_draw_count_frames']} frames with different "
              "global GO vs local Saturn AI draw counts "
              "(NOT equivalent streams)")
    if not report["observed_attacks_on_both_sides"]:
        print("Warning: attacks were not observed on both sides; "
              "inspect source trace and scenario before drawing conclusions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
