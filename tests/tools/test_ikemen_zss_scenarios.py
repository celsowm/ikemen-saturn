#!/usr/bin/env python3
"""ZSS oracle corpus invariants, including source parity for authored inputs."""
from __future__ import annotations

import json
from pathlib import Path

from tools.ikemen_oracle.inputs import build_timeline
from tools.ikemen_oracle.run_saturn import character_asset
from tools.ikemen_oracle.gen_scenarios import OUT

cases = sorted(OUT.glob("zss_*.json"))
strict = []
exploratory = []
for path in cases:
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["name"] == path.stem
    assert item.get("seed") == 1
    assert item.get("p1_ai") == 0 and item.get("p2_ai") == 0
    assert item.get("frames", 0) > 0
    assert len(build_timeline(item)) == item["frames"]
    assets = (character_asset(item["p1"]), character_asset(item["p2"]))
    assert "kfm_zss" in assets, (path, assets)
    assert assets in (("kfm", "kfm_zss"), ("kfm_zss", "kfm"))
    assert "pending" not in item, path
    if item.get("exploratory") is True:
        exploratory.append(path.stem)
        base = OUT / item["origin"]
        assert base.exists(), base
        original = json.loads(base.read_text(encoding="utf-8"))
        assert build_timeline(item) == build_timeline(original)
        if path.stem == "zss_p2_timeout_win_180":
            # The upstream trace goes straight to 181 on the next visible
            # frame. State 180 is transitory within one simulation tick.
            assert item["expect"] == {
                "p1_states": [181], "p2_states": [170],
            }
        else:
            assert item.get("expect") == original.get("expect")
        assert item.get("setup") == original.get("setup")
    else:
        strict.append(path.stem)

assert set(strict) == {
    "zss_p1_stand_x_160", "zss_p2_stand_x_200",
    "zss_p2_fast_palm_240", "zss_p2_idle_120",
    "zss_p1_crouch_a_160", "zss_p1_special_qcf_a_200",
    "zss_p2_guard_stand_y_160", "zss_p2_ko_upper_y_420",
    "zss_p2_recovery_200", "zss_p2_throw_victim_160",
    "zss_p2_upper_y_200", "zss_p2_upper_y_attacker_200",
    "zss_p2_timeout_win_180",
}
assert exploratory == []
# Require each observed state in the full hit-reaction sequence, preventing
# vacuous PASSes that only execute 1025 without reaching the wall.
palm = json.loads((OUT / "zss_p2_fast_palm_240.json").read_text())
assert palm["expect"]["p2_states"] == [1025, 1026, 1027, 1028]
thrown = json.loads((OUT / "zss_p2_throw_victim_160.json").read_text())
assert thrown["expect"]["p2_states"] == [820, 821, 5100]
timeout = json.loads((OUT / "zss_p2_timeout_win_180.json").read_text())
assert timeout["expect"]["p1_states"] == [181]
assert timeout["expect"]["p2_states"] == [170]
print("ZSS oracle corpus: 13 upstream-proven strict scenarios OK")
