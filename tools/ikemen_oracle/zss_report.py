#!/usr/bin/env python3
"""Diagnostics for *upstream* Ikemen GO vs Saturn on mixed KFM/ZSS matches.

Do not compare classic KFM against ZSS as if their gameplay were identical.
Each report summarizes the same authored character selection in both engines.
Metadata tick/RNG are deliberately excluded as in diff.py.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

try:
    from .diff import compare, load_jsonl
except ImportError:
    from diff import compare, load_jsonl

FIELDS = (
    "state_no", "state_time", "state_type", "move_type", "ctrl",
    "anim", "anim_elem", "anim_time", "pos", "vel", "facing",
    "life", "power", "juggle", "hit_pause", "move_contact_type",
    "move_contact_time", "gethit_chain_id", "targets", "hitdef_targets",
)


def _root(row: dict, side: int) -> dict:
    matched = [
        c for c in row.get("chars", [])
        if c.get("player_no") == side and c.get("helper_index", 0) == 0
    ]
    if len(matched) != 1:
        raise ValueError(f"expected one P{side+1} root, got {len(matched)}")
    return matched[0]


def summarize(
    upstream: list[dict],
    saturn: list[dict],
    pos_eps: float = 1.5,
    vel_eps: float = 0.35,
) -> dict:
    if not upstream or not saturn:
        raise ValueError("both upstream and Saturn traces must be nonempty")

    metrics = {
        "schema": 1,
        "frames_upstream": len(upstream),
        "frames_saturn": len(saturn),
        "frames_compared": min(len(upstream), len(saturn)),
        "first_difference": None,
        "mismatches": {"global": {}, "p1": {}, "p2": {}},
        "examples": [],
    }
    counters = {"global": Counter(), "p1": Counter(), "p2": Counter()}

    def eps_for(field: str) -> float:
        if ".pos[" in field:
            return pos_eps
        if ".vel[" in field:
            return vel_eps
        return 1e-4

    for frame_no, (expected, actual) in enumerate(zip(upstream, saturn)):
        if expected.get("schema") != 1 or actual.get("schema") != 1:
            raise ValueError(f"frame {frame_no}: trace schema must be 1")
        fields = [("global", "round_state",
                   expected.get("round_state"), actual.get("round_state"))]
        for side, label in ((0, "p1"), (1, "p2")):
            a, b = _root(expected, side), _root(actual, side)
            fields.extend(
                (label, key, a.get(key), b.get(key)) for key in FIELDS
            )
        fields.append(("global", "projectiles",
                       expected.get("projectiles"),
                       actual.get("projectiles")))
        for label, name, a, b in fields:
            differences: list[str] = []
            compare(a, b, f"{label}.{name}", differences,
                    eps_for, 1)
            if differences:
                counters[label][name] += 1
                finding = {
                    "frame": frame_no, "side": label, "field": name,
                    "detail": differences[0],
                }
                if metrics["first_difference"] is None:
                    metrics["first_difference"] = finding
                if len(metrics["examples"]) < 8:
                    metrics["examples"].append(finding)
    for label, counts in counters.items():
        metrics["mismatches"][label] = dict(sorted(
            counts.items(), key=lambda pair: (-pair[1], pair[0])))
    if len(upstream) != len(saturn):
        metrics["mismatches"]["global"]["trace_length"] = abs(
            len(upstream) - len(saturn))
        if metrics["first_difference"] is None:
            metrics["first_difference"] = {
                "frame": min(len(upstream), len(saturn)),
                "side": "global", "field": "trace_length",
                "detail": "upstream and Saturn trace lengths differ",
            }
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    parser.add_argument("saturn", type=Path)
    parser.add_argument("--pos-eps", type=float, default=1.5)
    parser.add_argument("--vel-eps", type=float, default=0.35)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        metrics = summarize(load_jsonl(args.upstream),
                            load_jsonl(args.saturn),
                            args.pos_eps, args.vel_eps)
    except (ValueError, KeyError) as exc:
        print(f"ZSS parity report invalid: {exc}", file=sys.stderr)
        return 2

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2) + "\n",
                            encoding="utf-8")
    first = metrics["first_difference"]
    if first is None:
        print(f"ZSS parity MATCH: {metrics['frames_compared']} frames")
    else:
        print(f"ZSS parity first mismatch: frame {first['frame']} "
              f"{first['side']}.{first['field']} ({first['detail']})")
        for side, fields in metrics["mismatches"].items():
            if fields:
                print(f"  {side}: " + ", ".join(
                    f"{field}={count}f" for field, count
                    in list(fields.items())[:6]))
    # Nonzero means a report could not be generated, not that gameplay differs.
    # suite.py is solely responsible for the pass/pending/fail decision.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
