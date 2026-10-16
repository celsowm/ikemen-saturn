#!/usr/bin/env python3
"""Verify genuine ZSS state bodies, conversion and fail-closed behavior."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_cns import parse_state  # noqa: E402
from tools.ikemen_zss_character_states import compile_zss_overrides  # noqa: E402

folder = ROOT / ".external" / "Ikemen-GO-Screenpack" / "chars" / "kfm_zss"
character = folder / "kfm.zss"
hits = folder / "hits.zss"
overrides = compile_zss_overrides(character, hits)
assert set(overrides) == {170, 180, 820, 1025}

expected = {
    170: ("IK_CNS_CTRL_NOT_HIT_BY",),
    180: ("IK_CNS_CTRL_CHANGE_STATE",),
    820: ("IK_CNS_CTRL_CHANGE_ANIM2", "IK_CNS_CTRL_SELF_STATE"),
    1025: ("IK_CNS_CTRL_CHANGE_ANIM2", "IK_CNS_CTRL_CHANGE_STATE"),
}
for number, (state, controllers) in overrides.items():
    row, *emitted = parse_state(state, 0, 0, 0, 0, 0, 0, 0)
    assert row["number"] == number
    assert row["controller_count"] == 0
    assert row["unsupported_controllers"] == []
    assert all(not values for values in emitted)
    assert tuple(x["type"] for x in controllers) == expected[number]
    assert all(x["state_number"] == number for x in controllers)

assert overrides[170][0].statedef.get("anim") == "170"
assert overrides[180][0].statedef.get("anim") == "-2"
assert overrides[820][1][1]["trigger_kind"] == "IK_CNS_TRIGGER_NOT_BOUND"
assert overrides[1025][1][1]["trigger_kind"] == "IK_CNS_TRIGGER_HIT_SHAKE_OVER"

# A new ZSS controller or missing semantic branch must break generation;
# never let a partially compiled move masquerade as source parity.
with tempfile.TemporaryDirectory() as temp:
    modified = Path(temp) / "kfm.zss"
    modified.write_text(
        character.read_text(encoding="utf-8-sig").replace(
            "changeState{value: 181; ctrl: 0}",
            "changeState{value: 181; ctrl: 1}", 1),
        encoding="utf-8")
    assert modified.read_text() != character.read_text(encoding="utf-8-sig")
    try:
        compile_zss_overrides(modified, hits)
    except ValueError as e:
        assert "state 180 body changed" in str(e)
    else:
        raise AssertionError("changed ZSS controller accepted")

print("ZSS state compiler: native 170/180/820/1025 OK, fail-closed source check OK")
