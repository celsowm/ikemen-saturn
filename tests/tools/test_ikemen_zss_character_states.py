#!/usr/bin/env python3
"""Verify genuine ZSS state bodies, conversion and fail-closed behavior."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_cns import parse_state, q16  # noqa: E402
from tools.ikemen_zss_character_states import (
    compile_zss_overrides, patch_air_punch_ctrl_timing,
)  # noqa: E402

folder = ROOT / ".external" / "Ikemen-GO-Screenpack" / "chars" / "kfm_zss"
character = folder / "kfm.zss"
hits = folder / "hits.zss"
overrides = compile_zss_overrides(character, hits)
assert set(overrides) == {170, 180, 1061, 820, 821, 1025, 1026, 1027, 1028}

expected = {
    170: ("IK_CNS_CTRL_NOT_HIT_BY",),
    180: ("IK_CNS_CTRL_CHANGE_STATE",),
    1061: ("IK_CNS_CTRL_VEL_ADD", "IK_CNS_CTRL_CHANGE_STATE",
           "IK_CNS_CTRL_CHANGE_STATE"),
    820: ("IK_CNS_CTRL_CHANGE_ANIM2", "IK_CNS_CTRL_SELF_STATE"),
    1025: ("IK_CNS_CTRL_CHANGE_ANIM2", "IK_CNS_CTRL_CHANGE_STATE"),
    821: ("IK_CNS_CTRL_VEL_ADD", "IK_CNS_CTRL_CHANGE_STATE",
          "IK_CNS_CTRL_SELF_STATE", "IK_CNS_CTRL_SELF_STATE"),
    1026: ("IK_CNS_CTRL_HIT_VEL_SET", "IK_CNS_CTRL_VEL_ADD",
           "IK_CNS_CTRL_SCREEN_BOUND", "IK_CNS_CTRL_CHANGE_STATE",
           "IK_CNS_CTRL_SELF_STATE"),
    1028: ("IK_CNS_CTRL_NOT_HIT_BY", "IK_CNS_CTRL_VEL_SET",
           "IK_CNS_CTRL_TURN", "IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS",
           "IK_CNS_CTRL_VEL_ADD", "IK_CNS_CTRL_CHANGE_ANIM_DESCENT_IF_EXISTS",
           "IK_CNS_CTRL_SELF_STATE"),
    1027: ("IK_CNS_CTRL_TURN", "IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE",
           "IK_CNS_CTRL_SCREEN_BACK_EFFECT", "IK_CNS_CTRL_SOUND_EVENT",
           "IK_CNS_CTRL_CHANGE_ANIM2", "IK_CNS_CTRL_POS_FREEZE",
           "IK_CNS_CTRL_SCREEN_BOUND", "IK_CNS_CTRL_CHANGE_STATE"),
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
assert overrides[1061][0].statedef.get("hitdefpersist") == "1"
assert overrides[1061][0].statedef.get("velset") == "2, -7.5"
knee = overrides[1061][1]
assert knee[0]["value5"] == q16(0.45)
assert knee[1]["trigger_kind"] == "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8"
assert knee[1]["trigger_value"] == (1 << 5) | (1 << 6)
assert knee[1]["trigger_value2"] == -256
assert knee[1]["value0"] == 1055
assert knee[2]["trigger_kind"] == "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL"
assert knee[2]["trigger_value"] == -10 * 256
assert knee[2]["value0"] == 1052
assert overrides[820][1][1]["trigger_kind"] == "IK_CNS_TRIGGER_NOT_BOUND"
assert overrides[1025][1][1]["trigger_kind"] == "IK_CNS_TRIGGER_HIT_SHAKE_OVER"
assert overrides[821][1][1]["trigger_kind"] == "IK_CNS_TRIGGER_THROW_GROUND_RECOVERY"
assert overrides[821][1][2]["trigger_kind"] == "IK_CNS_TRIGGER_THROW_AIR_RECOVERY"
assert overrides[821][1][1]["value0"] == 5200
assert overrides[821][1][2]["value0"] == 5210
assert overrides[821][1][3]["value0"] == 5100
assert overrides[821][1][0]["value5"] == q16(0.4)
assert overrides[1026][1][1]["value5"] == q16(0.45)
assert overrides[1026][1][2]["trigger_kind"] == "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE_LT"
assert overrides[1026][1][3]["trigger_kind"] == "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE"
assert overrides[1026][1][3]["value0"] == 1027
assert overrides[1028][1][0]["type"] == "IK_CNS_CTRL_NOT_HIT_BY"
assert "IK_CNS_ATTR_NORMAL" in overrides[1028][1][0]["value0"]
assert overrides[1028][1][3]["value0"] == 5052
assert overrides[1028][1][3]["value1"] == 5050
assert overrides[1028][1][5]["value2"] == 10
assert overrides[1028][1][5]["value3"] == 1
assert overrides[1028][1][5]["value0"] == -2 * 256
wall = overrides[1027][1]
assert wall[0]["trigger_kind"] == "IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE"
assert wall[1]["value0"] == 15 * 256 and wall[1]["value1"] == 1
assert wall[2]["value0"] == 72 and wall[2]["value1"] == -50
assert wall[3]["value0"] == 7 and wall[3]["value1"] == 0
assert wall[4]["value0"] == 1027
assert wall[5]["flags"] == "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y"
assert wall[7]["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_END"
assert wall[7]["value0"] == 1028

# State 600 remains classic CNS for sound/HitDef, but its ZSS CtrlSet
# has different timing. Only the verified CtrlSet may change.
classic_600 = [
    {"type": "IK_CNS_CTRL_CTRL_SET", "trigger_kind": "IK_CNS_TRIGGER_TIME_EQ",
     "trigger_value": 17, "trigger_value2": 0, "value0": 1},
]
patched_600 = patch_air_punch_ctrl_timing(character, classic_600)
assert classic_600[0]["trigger_kind"] == "IK_CNS_TRIGGER_TIME_EQ"
assert patched_600[0]["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED"
assert patched_600[0]["trigger_value"] == (3 << 8) | 2
assert patched_600[0]["value0"] == 1
assert patched_600[0] is not classic_600[0]

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    before, state = original.split("[StateDef 600;", 1)
    assert "if animElemTime(3) = 2" in state
    modified = Path(temp) / "kfm.zss"
    modified.write_text(
        before + "[StateDef 600;" +
        state.replace("if animElemTime(3) = 2",
                      "if animElemTime(3) = 3", 1),
        encoding="utf-8")
    try:
        patch_air_punch_ctrl_timing(modified, classic_600)
    except ValueError as exc:
        assert "state 600 CtrlSet clause changed" in str(exc)
    else:
        raise AssertionError("changed state 600 ZSS CtrlSet accepted")

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

# Reject changed airborne knee cancel logic, wall detection or throw recovery.
with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    old = 'if (command = "a" || command = "b") && !aiLevelF && vel y < -1'
    assert old in original
    modified = Path(temp) / "kfm.zss"
    before, state_1061 = original.split("[StateDef 1061;", 1)
    assert old in state_1061
    modified.write_text(
        before + "[StateDef 1061;" +
        state_1061.replace(old, old.replace("-1", "-2"), 1),
        encoding="utf-8")
    try:
        compile_zss_overrides(modified, hits)
    except ValueError as exc:
        assert "state 1061 body changed" in str(exc)
    else:
        raise AssertionError("changed ZSS knee state 1061 accepted")

# Reject changed wall detection or airborne throw-recovery behavior.
with tempfile.TemporaryDirectory() as temp:
    original = hits.read_text(encoding="utf-8-sig")
    for old, new, number in (
        ("backEdgeBodyDist < 65", "backEdgeBodyDist < 66", 1026),
        ("pos y >= -20", "pos y >= -15", 821),
        ("velAdd{y: .35}", "velAdd{y: .5}", 1028),
        ("call SysSnd(7, 0, 1);", "call SysSnd(7, 1, 1);", 1027),
    ):
        changed = Path(temp) / "hits.zss"
        assert old in original
        changed.write_text(original.replace(old, new, 1), encoding="utf-8")
        try:
            compile_zss_overrides(character, changed)
        except ValueError as exc:
            assert f"state {number} body changed" in str(exc)
        else:
            raise AssertionError(f"changed ZSS state {number} accepted")

print("ZSS state compiler: native 170/180/1061/820/821/1025/1026/1027/1028 OK")
