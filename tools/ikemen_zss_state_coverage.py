#!/usr/bin/env python3
"""Inventory the pinned ZSS state bodies against the native lowering set.

Single responsibility: enumerate `[StateDef N]` sections in the pinned
screenpack checkout and classify each number as native (compiled by
tools/ikemen_zss_character_states.py) or classic-CNS fallback. One line
per state. Coverage does not imply parity; oracle scenarios prove that
separately.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.ikemen_cns import parse_zss_states
from tools.ikemen_zss_character_states import CHARACTER_STATES, HIT_STATES

ROOT = sys.path[0]
# cmake/IkemenAssets.cmake pins this checkout as the lowering source of
# truth. chars/kfm_zaxis is a newer 3-axis development copy and is NOT the
# port target.
CHAR_DIR = (Path(sys.path[0]) / ".external" / "Ikemen-GO-Screenpack"
            / "chars" / "kfm_zss")

FILES = ("kfm.zss", "hits.zss")
LABELS = ("native", "remaining")


def inventory(char_dir: Path) -> dict:
    """Classify every statedef number found in the pinned ZSS sources.

    Numbers present in both files are attributed to the native side
    when either copy is natively lowered.
    """
    native = set(CHARACTER_STATES) | set(HIT_STATES)
    sources: dict[int, set[str]] = {}
    for relative in FILES:
        path = char_dir / relative
        states = parse_zss_states(path)
        for number in states:
            sources.setdefault(number, set()).add(relative)
    rows = {
        "native": sorted(n for n in sources if n in native),
        "remaining": sorted(n for n in sources if n not in native),
        "sources": {number: sorted(files)
                    for number, files in sources.items()},
    }
    return rows


def fmt(rows: dict, remaining_only: bool = False) -> None:
    for label in LABELS:
        if remaining_only and label != "remaining":
            continue
        numbers = rows[label]
        print(f"{label}: {len(numbers)}")
        for number in numbers:
            origin = "+".join(rows["sources"][number])
            print(f"{label:<10}{number:5}  {origin}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=CHAR_DIR,
                        help="character directory (default: pinned checkout)")
    parser.add_argument("--json", action="store_true",
                        help="emit rows as one JSON object")
    parser.add_argument("--remaining-only", action="store_true",
                        help="print only the fallback list")
    args = parser.parse_args()

    missing = [name for name in FILES
               if not (args.dir / name).is_file()]
    if missing:
        print("missing ZSS sources: " + ", ".join(missing), file=sys.stderr)
        return 2

    rows = inventory(args.dir)
    if args.json:
        print(json.dumps({label: numbers for label, numbers in rows.items()
                          if label in LABELS} | {"sources": rows["sources"]}))
    else:
        fmt(rows, args.remaining_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
