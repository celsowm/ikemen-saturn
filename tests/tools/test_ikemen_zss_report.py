#!/usr/bin/env python3
"""Ensure ZSS parity reports identify meaningful engine divergences."""
from __future__ import annotations

from tools.ikemen_oracle.run_saturn import character_asset
from tools.ikemen_oracle.zss_report import summarize


def row(*, pos=12.0, life=1000, state=200, anim=200):
    return {
        "schema": 1, "round_state": 2, "projectiles": [],
        "chars": [
            {"player_no": 0, "helper_index": 0, "state_no": state,
             "life": life, "pos": [pos, 0.0, 0.0],
             "vel": [0.5, 0.0, 0.0], "anim": anim},
            {"player_no": 1, "helper_index": 0, "state_no": 0,
             "life": 1000, "pos": [100.0, 0.0, 0.0],
             "vel": [0.0, 0.0, 0.0], "anim": 0},
        ],
    }


assert character_asset("../Ikemen-GO-Screenpack/chars/kfm/kfm.def") == "kfm"
assert character_asset("../Ikemen-GO-Screenpack/chars/kfm_zss/kfm_zss.def") == "kfm_zss"
assert character_asset("chars/kfm_zss/kfm_zss.def") == "kfm_zss"
for bad in ("chars/kfm_zss/kfm.def", "chars/kfm/other.def",
            "chars/other/other.def", "missing.def"):
    try:
        character_asset(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"unsupported character accepted: {bad}")

base = [row(), row()]
same = summarize(base, [row(), row()])
assert same["first_difference"] is None
assert all(not x for x in same["mismatches"].values())

within_eps = summarize(base, [row(pos=13.4), row(pos=11.9)])
assert within_eps["first_difference"] is None

diff = summarize(base, [row(life=995, pos=14.0), row(life=995, pos=14.0)])
assert diff["first_difference"] == {
    "frame": 0, "side": "p1", "field": "pos",
    "detail": "p1.pos[0]: expected 12.0, got 14.0",
}
assert diff["mismatches"]["p1"] == {"life": 2, "pos": 2}
assert not diff["mismatches"]["p2"]

length = summarize(base, [row()])
assert length["frames_compared"] == 1
assert length["mismatches"]["global"]["trace_length"] == 1
try:
    summarize([], base)
except ValueError:
    pass
else:
    raise AssertionError("empty traces should fail")

print("KFM ZSS oracle report: asset rejection, float drift and frame diagnostics OK")
