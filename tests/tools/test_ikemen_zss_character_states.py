#!/usr/bin/env python3
"""Verify genuine ZSS state bodies, conversion and fail-closed behavior."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_cns import (collect_states, constants, parse_sections,
                              parse_state, q16)  # noqa: E402
from tools.ikemen_zss_character_states import (
    compile_zss_overrides,
    zss_row_patch,
)  # noqa: E402

folder = ROOT / ".external" / "Ikemen-GO-Screenpack" / "chars" / "kfm_zss"
character = folder / "kfm.zss"
hits = folder / "hits.zss"
const_globals, _ = collect_states(parse_sections(folder / "kfm.const"))
CONST = constants(const_globals)


def compile_overrides(character_zss, hits_zss):
    return compile_zss_overrides(character_zss, hits_zss, CONST)


overrides = compile_overrides(character, hits)
assert set(overrides) == {20, 100, 170, 180, 181, 195, 200, 800, 810, 210, 230, 240, 400, 410, 430, 440, 600, 610, 630, 640, 1000, 1010, 1020, 1050, 1051, 1052, 1055, 1056, 1060, 1061, 1070, 1071, 1075, 1100, 1110, 1120, 1200, 1210, 1220, 1400, 1410, 1420, 820, 821, 1025, 1026, 1027, 1028}

expected = {
    20: ("IK_CNS_CTRL_VEL_SET", "IK_CNS_CTRL_VEL_SET",
         "IK_CNS_CTRL_CHANGE_ANIM_BY_VX"),
    100: ("IK_CNS_CTRL_VEL_SET", "IK_CNS_CTRL_CHANGE_STATE"),
    170: ("IK_CNS_CTRL_NOT_HIT_BY",),
    180: ("IK_CNS_CTRL_CHANGE_STATE",),
    181: ("IK_CNS_CTRL_ASSERT_ROUND_NOT_OVER", "IK_CNS_CTRL_NOT_HIT_BY"),
    195: ("IK_CNS_CTRL_CTRL_SET", "IK_CNS_CTRL_CHANGE_STATE"),
    200: (), 800: (), 810: (),
    210: (),
    230: (),
    240: (),
    400: (),
    410: (),
    430: (),
    440: (),
    600: (),
    610: (),
    630: (),
    640: (),
    1000: (),
    1010: (),
    1020: (),
    1100: (), 1110: (), 1120: (), 1200: (), 1210: (), 1220: (), 1400: (), 1410: (), 1420: (),
    1070: (), 1071: (), 1075: (),
    1050: (),
    1060: (),
    1051: ("IK_CNS_CTRL_VEL_ADD", "IK_CNS_CTRL_CHANGE_STATE",
           "IK_CNS_CTRL_CHANGE_STATE"),
    1052: ("IK_CNS_CTRL_POS_SET", "IK_CNS_CTRL_SOUND_EVENT", "IK_CNS_CTRL_CTRL_SET",
           "IK_CNS_CTRL_POS_ADD", "IK_CNS_CTRL_CHANGE_STATE"),
    1055: (),
    1056: ("IK_CNS_CTRL_POS_SET", "IK_CNS_CTRL_SOUND_EVENT", "IK_CNS_CTRL_CHANGE_STATE"),
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
    if number in (800, 810):
        hitdefs, sounds, controls, *rest = emitted
        assert row["unsupported_controllers"] == []
        if number == 800:
            # Miss-priority throw HitDef at Time 0 plus the idle return.
            assert len(hitdefs) == 1 and len(sounds) == 0 and len(controls) == 1
            assert hitdefs[0]["p1_state_no"] == 810
            assert hitdefs[0]["p2_state_no"] == 820
            assert hitdefs[0]["trigger_kind"] == "IK_CNS_TRIGGER_TIME_EQ"
        else:
            assert len(hitdefs) == 0 and len(sounds) == 2
        continue
    if number in (1070, 1071, 1075):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == 1 and len(sounds) == (2 if number == 1075 else 1 if number == 1070 else 0)
        assert len(controls) == 6 and row["unsupported_controllers"] == []
        if number == 1071:
            cancel = next(c for c in controls if c["type"] == "IK_CNS_CTRL_CHANGE_STATE" and c["value0"] == 1075)
            assert cancel["trigger_kind"] == "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8_AFTER_ENTRY"
        assert all(not values for values in rest)
        continue
    if number in (1400, 1410, 1420):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == (2 if number == 1420 else 1)
        assert len(sounds) == 1 and len(controls) == (7 if number == 1420 else 4)
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (1120, 1220):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == (2 if number == 1120 else 1)
        assert len(sounds) == 1 and len(controls) == (5 if number == 1120 else 7)
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (1100, 1110, 1200, 1210):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == (2 if number in (1100, 1110) else 1)
        assert len(sounds) == 1 and len(controls) == (2 if number in (1100, 1110) else 4)
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number == 1020:
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == 1 and len(sounds) == 1 and len(controls) == 9
        assert hitdefs[0]["trigger_value"] == 4 and hitdefs[0]["damage"] == 95
        assert [c["type"] for c in controls[:4]] == ["IK_CNS_CTRL_VEL_MUL_X_BY_ANIM_ELEM", "IK_CNS_CTRL_AFTER_IMAGE", "IK_CNS_CTRL_PAL_FX", "IK_CNS_CTRL_AFTER_IMAGE_TIME"]
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (1000, 1010, 1050, 1060):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == (2 if number in (1000, 1010) else 1)
        assert len(sounds) == 1
        assert len(controls) == {1000: 5, 1010: 5, 1050: 2, 1060: 3}[number]
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (210, 240, 410):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == (2 if number == 410 else 1) and len(sounds) == 1
        assert len(controls) == {210: 4, 240: 2, 410: 1}[number]
        assert [h["trigger_value"] for h in hitdefs] == ([3, 4] if number == 410 else [3])
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (600, 610, 630, 640):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == 1 and len(sounds) == 1 and len(controls) == (1 if number == 600 else 0)
        assert hitdefs[0]["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_ELEM_EQ"
        assert hitdefs[0]["trigger_value"] == (3 if number == 610 else 2)
        assert hitdefs[0]["damage"] == {600: 20, 610: 72, 630: 26, 640: 70}[number]
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number in (200, 230, 400, 430, 440):
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == 1 and len(sounds) == 1 and len(controls) == (2 if number == 400 else 1)
        assert hitdefs[0]["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_ELEM_EQ"
        assert hitdefs[0]["trigger_value"] == {200: 3, 230: 3, 400: 2, 430: 3, 440: 4}[number]
        assert hitdefs[0]["damage"] == {200: 23, 230: 26, 400: 23, 430: 28, 440: 72}[number]
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    if number == 1055:
        hitdefs, sounds, controls, *rest = emitted
        assert len(hitdefs) == 1 and len(sounds) == 2 and len(controls) == 3
        assert hitdefs[0]["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_ELEM_EQ"
        assert hitdefs[0]["trigger_value"] == 5
        assert hitdefs[0]["alt_damage"] == 40
        assert row["owns_air_accel"] == 1
        assert row["unsupported_controllers"] == []
        assert all(not values for values in rest)
        continue
    assert row["controller_count"] == 0
    assert row["unsupported_controllers"] == []
    assert all(not values for values in emitted)
    assert tuple(x["type"] for x in controllers) == expected[number]
    assert all(x["state_number"] == number for x in controllers)

# Walk and run lower to the shared locomotion rows with resolved constants;
# the omitted ctrl/movetype and the explicit NoWalk/NoAutoTurn assert are
# supplied by the fixed row patch, not invented per character.
row20 = parse_state(overrides[20][0], 0, 0, 0, 0, 0, 0, 0)[0]
row100 = parse_state(overrides[100][0], 0, 0, 0, 0, 0, 0, 0)[0]
assert row20["anim"] == -1 and row20["spr_priority"] == 0
assert row100["anim"] == 100 and row100["spr_priority"] == 1
assert zss_row_patch(20) == {"move_type": "IK_CNS_MOVE_IDLE", "ctrl": 1}
assert zss_row_patch(100)["assert_special_flags"] == (
    "IK_CNS_STATE_ASSERT_NO_WALK | IK_CNS_STATE_ASSERT_NO_AUTO_TURN")
assert zss_row_patch(100)["ctrl"] == 1
assert zss_row_patch(170) == {} and zss_row_patch(181) == {}
walk_back, walk_fwd, anim = overrides[20][1]
assert walk_back["trigger_value"] == "IK_CNS_COMMAND_HOLD_BACK"
assert walk_back["value0"] == CONST["walk_back_q8"]
assert walk_fwd["trigger_value"] == "IK_CNS_COMMAND_HOLD_FWD"
assert walk_fwd["value0"] == CONST["walk_fwd_q8"]
assert anim["value0"] == -1 and anim["value1"] == 20
run_vel, run_exit = overrides[100][1]
assert run_vel["value0"] == CONST["run_fwd_x_q8"]
assert run_exit["trigger_value"] == "IK_CNS_COMMAND_HOLD_FWD"
assert run_exit["trigger_kind"] == "IK_CNS_TRIGGER_COMMAND_INACTIVE"

assert overrides[170][0].statedef.get("anim") == "170"
assert overrides[180][0].statedef.get("anim") == "-2"
assert overrides[200][0].statedef.get("movetype") == "A"
assert overrides[200][0].statedef.get("juggle") == "1"
assert overrides[200][0].statedef.get("poweradd") == "10"
assert overrides[195][1][1]["flags"] == "IK_CNS_CTRL_HAS_CTRL | IK_CNS_CTRL_CTRL_FROM_ROUND"
assert overrides[1061][0].statedef.get("hitdefpersist") == "1"
assert overrides[1051][0].statedef.get("velset") == "2, -6"
assert overrides[1052][1][2]["trigger_value"] == (3 << 8) | 255
assert overrides[1052][1][3]["trigger_value"] == 4
assert overrides[1052][1][3]["value0"] == -15 * 256
assert overrides[1056][1][1]["value0"] == 40
assert overrides[1056][1][2]["flags"] == "IK_CNS_CTRL_HAS_CTRL | IK_CNS_CTRL_CTRL_FROM_ROUND"
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

# A new ZSS controller or missing semantic branch must break generation;
# never let a partially compiled move masquerade as source parity.
with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    assert "ctrl: roundState > 1" in original
    modified = Path(temp) / "kfm.zss"
    modified.write_text(original.replace("ctrl: roundState > 1", "ctrl: 1", 1), encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "EndState function changed" in str(exc)
    else:
        raise AssertionError("changed EndState function accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    anchor = "#Used to call system sounds from the screenpack"
    assert anchor in original
    modified = Path(temp) / "kfm.zss"
    modified.write_text(original.replace(anchor, "ctrlSet{value: 1}\n" + anchor, 1), encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "EndState function changed" in str(exc)
    else:
        raise AssertionError("extra EndState controller accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    old = "playSnd{value: S $bank, $sound; channel: $c}"
    assert old in original
    modified = Path(temp) / "kfm.zss"
    modified.write_text(original.replace(old, old.replace("$bank", "0", 1), 1), encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "CSnd function changed" in str(exc)
    else:
        raise AssertionError("changed CSnd function accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    old = "palFx{time: $time; add: 32, 16, 0; sinadd: 64, 32, 5, 3}"
    assert old in original
    modified = Path(temp) / "kfm.zss"
    modified.write_text(original.replace(old, old.replace("32, 16, 0", "31, 16, 0"), 1), encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "EXFX function changed" in str(exc)
    else:
        raise AssertionError("changed EXFX function accepted")
with tempfile.TemporaryDirectory() as temp:
    modified = Path(temp) / "kfm.zss"
    modified.write_text(
        character.read_text(encoding="utf-8-sig").replace(
            "changeState{value: 181; ctrl: 0}",
            "changeState{value: 181; ctrl: 1}", 1),
        encoding="utf-8")
    assert modified.read_text() != character.read_text(encoding="utf-8-sig")
    try:
        compile_overrides(modified, hits)
    except ValueError as e:
        assert "state 180 body changed" in str(e)
    else:
        raise AssertionError("changed ZSS controller accepted")

# Reject changed airborne knee cancel logic, wall detection or throw recovery.
with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    for number, old, new in ((1100, "damage: 52, 4", "damage: 53, 4"),
                             (1120, "damage: 30, 4", "damage: 31, 4"),
                             (1210, "ground.cornerpush.veloff: -15", "ground.cornerpush.veloff: -14"),
                             (1220, "ground.cornerpush.veloff: -20", "ground.cornerpush.veloff: -19")):
        before, state = original.split(f"[StateDef {number};", 1)
        assert old in state
        modified = Path(temp) / "kfm.zss"
        modified.write_text(before + f"[StateDef {number};" + state.replace(old, new, 1), encoding="utf-8")
        try:
            compile_overrides(modified, hits)
        except ValueError as exc:
            assert f"state {number} body changed" in str(exc)
        else:
            raise AssertionError(f"changed ZSS state {number} accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    before, state_200 = original.split("[StateDef 200;", 1)
    assert "damage: 23, 0" in state_200
    modified = Path(temp) / "kfm.zss"
    modified.write_text(before + "[StateDef 200;" +
                        state_200.replace("damage: 23, 0", "damage: 24, 0", 1),
                        encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "state 200 body changed" in str(exc)
    else:
        raise AssertionError("changed ZSS standing punch accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    before, state_1055 = original.split("[StateDef 1055;", 1)
    assert "if animElem = 5" in state_1055
    modified = Path(temp) / "kfm.zss"
    modified.write_text(before + "[StateDef 1055;" +
                        state_1055.replace("if animElem = 5", "if animElem = 4", 1),
                        encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "state 1055 body changed" in str(exc)
    else:
        raise AssertionError("changed ZSS knee kick state accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    before, state_1052 = original.split("[StateDef 1052;", 1)
    assert "if animElem = 3, -1" in state_1052
    modified = Path(temp) / "kfm.zss"
    modified.write_text(before + "[StateDef 1052;" +
                        state_1052.replace("if animElem = 3, -1", "if animElem = 3, 0", 1),
                        encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "state 1052 body changed" in str(exc)
    else:
        raise AssertionError("changed ZSS knee landing state accepted")

with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    before, state_1051 = original.split("[StateDef 1051;", 1)
    assert "velAdd{y: .45}" in state_1051
    modified = Path(temp) / "kfm.zss"
    modified.write_text(before + "[StateDef 1051;" +
                        state_1051.replace("velAdd{y: .45}", "velAdd{y: .5}", 1),
                        encoding="utf-8")
    try:
        compile_overrides(modified, hits)
    except ValueError as exc:
        assert "state 1051 body changed" in str(exc)
    else:
        raise AssertionError("changed ZSS knee state 1051 accepted")

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
        compile_overrides(modified, hits)
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
            compile_overrides(character, changed)
        except ValueError as exc:
            assert f"state {number} body changed" in str(exc)
        else:
            raise AssertionError(f"changed ZSS state {number} accepted")

# Reject changed win-pose roundnotover timing in kfm.zss state 181.
with tempfile.TemporaryDirectory() as temp:
    original = character.read_text(encoding="utf-8-sig")
    for old, new in (
        ("animTime < -2", "animTime < -1"),
        ("assertSpecial{flag: roundnotover}", "assertSpecial{flag: roundEnd}"),
    ):
        changed = Path(temp) / "kfm.zss"
        assert old in original, old
        changed.write_text(original.replace(old, new, 1), encoding="utf-8")
        try:
            compile_overrides(changed, hits)
        except ValueError as exc:
            assert "ZSS state 181 body changed" in str(exc)
        else:
            raise AssertionError(f"changed ZSS state 181 accepted: {old!r}")

print("ZSS state compiler: 46 source-checked states OK")
