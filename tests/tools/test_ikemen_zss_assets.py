#!/usr/bin/env python3
"""Prove the KFM-ZSS compatibility bridge uses real, distinct input assets."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_cmd import parse_cmd  # noqa: E402
from tools.ikemen_cns import collect_states, constants, parse_sections  # noqa: E402

SCREENPACK = ROOT / ".external" / "Ikemen-GO-Screenpack" / "chars"
classic = parse_cmd(SCREENPACK / "kfm" / "kfm.cmd")
zss = parse_cmd(SCREENPACK / "kfm_zss" / "kfm.cmd")

# The temporary classic State -1 program embeds numeric command IDs. It is
# safe to use with the ZSS CMD only while this equality holds.
assert classic.names == zss.names, "ZSS CMD indices changed: rebuild State -1 from ZSS"
assert len(classic.patterns) == len(zss.patterns)
assert len(zss.patterns) <= 64

def motions(asset, name: str) -> list[list[list[str]]]:
    return [
        [[k.name for k in step.keys] for step in pattern.steps]
        for pattern in asset.patterns if pattern.name == name
    ]

for name in ("TripleKFPalm", "SmashKFUpper"):
    assert motions(classic, name) != motions(zss, name), (
        f"{name}: expected ZSS's distinct upstream motion")

for name in ("holdfwd", "holdback", "holdup", "holddown",
             "x", "y", "a", "b", "start", "recovery"):
    assert name in zss.names

globals_, states = collect_states(parse_sections(SCREENPACK / "kfm_zss" / "kfm.const"))
assert not states, "expected ZSS constants file, not classic CNS states"
for section in ("data", "size", "velocity", "movement"):
    assert section in globals_
c = constants(globals_)
assert c["life"] == 1000
assert c["air_juggle"] == 15
assert c["ground_back"] == 15
assert c["ground_front"] == 16
assert c["walk_fwd_q8"] > 0

print("ikemen ZSS CMD + native constants: OK (state bodies still compatibility fallback)")
