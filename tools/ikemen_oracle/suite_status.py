#!/usr/bin/env python3
"""Classify checked-in oracle scenarios against existing suite reports.

Single responsibility: read the JSON reports suite.py already produced.
It never runs engines, deletes files or decides vacuity -- that is
suite.py's job. One status line is printed per scenario so the output
stays greppable, and `--json` emits the same rows for tooling.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ROOT / "tools" / "ikemen_oracle" / "scenarios"
SUITES = ROOT / "build" / "ikemen_oracle" / "suite"

STATUSES = ("OK", "DIFF", "MISSING", "BROKEN")


def classify(scenario: Path, suite_dir: Path = SUITES) -> dict:
    """One row: scenario name, compared frames and first divergence."""
    item = json.loads(scenario.read_text(encoding="utf-8"))
    name = item["name"]
    report = suite_dir / name / "zss_report.json"
    row = {
        "scenario": name,
        "frames": item.get("frames"),
        "reported_frames": None,
        "first_difference": None,
        "status": "MISSING",
    }
    if not report.is_file():
        return row
    try:
        metrics = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        row["status"] = "BROKEN"
        return row
    first = metrics.get("first_difference")
    row["reported_frames"] = metrics.get("frames_compared")
    row["first_difference"] = first
    row["status"] = "DIFF" if first is not None else "OK"
    return row


def fmt(row: dict) -> str:
    detail = ""
    if row["status"] == "OK":
        detail = f"{row['reported_frames']} frames compared"
    elif row["status"] == "DIFF":
        first = row["first_difference"] or {}
        detail = (f"frame {first.get('frame')} "
                  f"{first.get('side')}.{first.get('field')} "
                  f"({first.get('detail')})")
    summary = detail if detail else f"{row['frames']} requested"
    return f"{row['status']:<7} {row['scenario']:<36} {summary}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("filter", nargs="*", help="name or prefix filter")
    parser.add_argument("--json", action="store_true",
                        help="emit rows as JSONL instead of a table")
    parser.add_argument("--dir", type=Path, default=SUITES,
                        help="suite output directory (default: build tree)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 unless every selected row is OK")
    args = parser.parse_args()

    paths = sorted(SCENARIOS.glob("*.json"))
    if args.filter:
        paths = [p for p in paths if p.stem.startswith(args.filter[0])]
    if not paths:
        print("no oracle scenarios matched", file=sys.stderr)
        return 2

    rows = [classify(path, args.dir) for path in paths]
    if args.json:
        for row in rows:
            print(json.dumps(row))
    else:
        for row in rows:
            print(fmt(row))
        counts = {status: 0 for status in STATUSES}
        for row in rows:
            counts[row["status"]] += 1
        print(f"{counts['OK']} OK, {counts['DIFF']} Diff, "
              f"{counts['MISSING']} Missing, {counts['BROKEN']} Broken")

    if args.strict and any(row["status"] != "OK" for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
