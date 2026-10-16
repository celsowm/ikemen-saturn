#!/usr/bin/env python3
"""Upstream-only AI trace metric contracts (no false Saturn parity)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.ikemen_oracle.ai_probe import summarize

root = Path(__file__).resolve().parents[2]
scenario = json.loads((
    root / "tools/ikemen_oracle/ai_scenarios/zss_ai_p2_pressure_360.json"
).read_text(encoding="utf-8"))
assert scenario["p2_ai"] == 8 and scenario["p1_ai"] == 0
assert "kfm_zss/kfm_zss.def" in scenario["p2"]
assert scenario["frames"] == 360

rows = [
    {"chars": [{"player_no": 0, "helper_index": 0, "state_no": 0,
                "move_type": 0},
               {"player_no": 1, "helper_index": 0, "state_no": 0,
                "move_type": 0}]},
    {"chars": [{"player_no": 0, "helper_index": 0, "state_no": 200,
                "move_type": 1},
               {"player_no": 1, "helper_index": 0, "state_no": 1060,
                "move_type": 1}]},
    {"chars": [{"player_no": 0, "helper_index": 0, "state_no": 200,
                "move_type": 1},
               {"player_no": 1, "helper_index": 0, "state_no": 1061,
                "move_type": 1}]},
]
r = summarize(rows)
assert r["frames"] == 3 and r["ai_player"] == 2
assert r["state_histogram"] == {"0": 1, "1060": 1, "1061": 1}
assert r["attack_frames"] == 2 and r["observed_attacks"]
assert [(x["from"], x["to"]) for x in r["state_transitions"]] == [
    (0, 1060), (1060, 1061)
]
assert "not Saturn parity" in r["reference"]
try:
    summarize([])
except ValueError:
    pass
else:
    raise AssertionError("empty AI trace accepted")
print("ZSS AI upstream-only observation metrics OK")
