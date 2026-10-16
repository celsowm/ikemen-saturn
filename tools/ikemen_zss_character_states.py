#!/usr/bin/env python3
"""Strict source-checked character-state lowering for KFM ZSS.

Only controllers already implemented by Ikemen Saturn are accepted.
Nine state bodies are translated, not merely their StateDef metadata.
Human throw recovery and strong-knee air follow-up are supported;
AI-random recovery is not yet modeled.
Other ZSS states keep the classic CNS fallback at runtime.

A source change invalidates the conversion until it has been reviewed
rather than silently introducing a behavior mismatch.
"""
from __future__ import annotations

import re
from pathlib import Path

from tools.ikemen_cns import (Section, State, _common_ctrl, parse_zss_states,
                              no_hit_by_attr_mask, no_hit_by_state_mask, q8, q16)

# Supported source bodies with every controller lowered in the exact order.
# Normalization discards insignificant spacing and ZSS '#' comments, but no
# executable token: any new controller causes a hard failure.
BODIES = {
    170: "nothitby{value:sca;time:1}",
    180: "changestate{value:181;ctrl:0}",
    1061: ('veladd{y:.45}'
           'if(command="a"||command="b")&&!ailevelf&&vely<-1{'
           'changestate{value:1055}}'
           'ifvely>0&&posy>=-10{changestate{value:1052}}'),
    820: ("iftime=0{changeanim2{value:820}}"
          "if!gethitvar(isbound){selfstate{value:5050}}"),
    1025: ("changeanim2{value:1025}"
           "ifhitshakeover=1{changestate{value:1026}}"),
    821: ('veladd{y:.4}'
          'ifvely>0&&alive&&canrecover&&(command="recovery"||random%5=0&&ailevelf){'
          'ifposy>=-20{changestate{value:5200}}'
          'else{selfstate{value:5210}}}'
          'ifposy>=0&&vely>0{selfstate{value:5100}}'),
    1026: ('iftime=0{hitvelset{x:1;y:1}}veladd{y:.45}'
           'ifposy<-15{'
           'ifbackedgebodydist<65||frontedgebodydist<65{'
           'screenbound{value:1;movecamera:0,1}}'
           'ifbackedgebodydist<=20||frontedgebodydist<=20{'
           'changestate{value:1027}}}'
           'ifvely>0&&posy>=0{selfstate{value:5100}}'),
    1028: ('nothitby{value:,na,np}iftime=0{'
           'velset{y:-6;x:1.6}ifbackedgedist<30{turn{}}'
           'if!selfanimexist(5052){changeanim{value:5050}}'
           'ifselfanimexist(5052){changeanim{value:5052}}}'
           'veladd{y:.35}ifvely>-2{'
           'persistent(0)ifanim=5050&&selfanimexist(5060){'
           'changeanim{value:5060}}'
           'persistent(0)ifanim=5052&&selfanimexist(5062){'
           'changeanim{value:5062}}}'
           'ifvely>0&&posy>=0{selfstate{value:5100}}'),
    1027: ('iftime=0{iffrontedgebodydist<=30{turn{}}'
           'posadd{x:15-backedgebodydist}'
           'explod{anim:f72;pos:0,floor(screenposy)-50;'
           'postype:back;sprpriority:3;}'
           'callsyssnd(7,0,1);changeanim2{value:1027}}'
           'posfreeze{}screenbound{value:1;movecamera:0,1}'
           'ifanimtime=0{changestate{value:1028}}'),
}

CHARACTER_STATES = (170, 180, 1061)
HIT_STATES = (820, 821, 1025, 1026, 1027, 1028)

# These guards protect against silently compiling outdated states with an
# incompatible move class, physics type or action.
METADATA = {
    170: {"type": "S", "movetype": "I", "physics": "S", "anim": "170", "ctrl": "0"},
    180: {"type": "S", "movetype": "I", "physics": "S", "anim": "-2", "ctrl": "0"},
    1061: {"type": "A", "movetype": "A", "physics": "N",
           "velset": "2,-7.5", "anim": "1051", "hitdefpersist": "1"},
    820: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
    1025: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
    821: {"type": "A", "movetype": "H", "physics": "N",
          "velset": "2.8,-7", "poweradd": "40"},
    1026: {"type": "A", "movetype": "H", "physics": "N"},
    1028: {"type": "A", "movetype": "H", "physics": "N"},
    1027: {"type": "A", "movetype": "H", "physics": "N"},
}


def normalize_body(source: str) -> str:
    # These selected states contain no quoted # characters.
    lines = [line.split("#", 1)[0] for line in source.splitlines()]
    return re.sub(r"\s+", "", "".join(lines)).lower()


def _controllers(state: int) -> list[dict]:
    if state == 170:
        # Invulnerable to S/C/A attackers for one tick (refreshed each tick).
        return [_common_ctrl(
            170, "IK_CNS_CTRL_NOT_HIT_BY",
            "IK_CNS_TRIGGER_ALWAYS", 0, 0, 7, 1)]
    if state == 180:
        return [_common_ctrl(
            180, "IK_CNS_CTRL_CHANGE_STATE",
            "IK_CNS_TRIGGER_ALWAYS", 0, 0, 181, 0,
            "IK_CNS_CTRL_HAS_CTRL")]
    if state == 1061:
        # Strong Knee: keep the previous HitDef while jumping, allow human
        # a/b air-kick follow-up on ascent, then land at Pos Y >= -10.
        # AI is not enabled in the current native fighter driver.
        return [
            _common_ctrl(
                1061, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.45),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.45)),
            _common_ctrl(
                1061, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8",
                (1 << 5) | (1 << 6), q8(-1), 1055),
            _common_ctrl(
                1061, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL", q8(-10), 0, 1052),
        ]
    if state == 820:
        return [
            _common_ctrl(
                820, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 820),
            _common_ctrl(
                820, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_NOT_BOUND", 0, 0, 5050),
        ]
    if state == 1025:
        return [
            _common_ctrl(
                1025, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 1025),
            _common_ctrl(
                1025, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 1026),
        ]
    if state == 821:
        # Source chooses ground recovery first (Pos Y >= -20), then airborne
        # recovery, then ground collision. Random AI recovery remains deferred.
        return [
            _common_ctrl(
                821, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.4),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.4)),
            _common_ctrl(
                821, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_THROW_GROUND_RECOVERY", q8(-20),
                0, 5200),
            _common_ctrl(
                821, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_THROW_AIR_RECOVERY", 0, 0, 5210),
            _common_ctrl(
                821, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    if state == 1026:
        return [
            _common_ctrl(
                1026, "IK_CNS_CTRL_HIT_VEL_SET",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y"),
            _common_ctrl(
                1026, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.45),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.45)),
            _common_ctrl(
                1026, "IK_CNS_CTRL_SCREEN_BOUND",
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE_LT", q8(-15),
                65, 1, 0, value2=1, value3=3),
            _common_ctrl(
                1026, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE", q8(-15),
                20, 1027),
            _common_ctrl(
                1026, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    if state == 1027:
        # Script order matters: turn first, compute the new back-body
        # distance for PosAdd (not the pre-turn context), then F72 and
        # common-system SND (7,0). Screen Y is fixed in the Saturn stage.
        return [
            _common_ctrl(
                1027, "IK_CNS_CTRL_TURN",
                "IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE", 30),
            _common_ctrl(
                1027, "IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, q8(15), 1),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SCREEN_BACK_EFFECT",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 72, -50),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SOUND_EVENT",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 7, 0),
            _common_ctrl(
                1027, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 1027),
            _common_ctrl(
                1027, "IK_CNS_CTRL_POS_FREEZE",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y"),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SCREEN_BOUND",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 1, 0,
                value2=1, value3=3),
            _common_ctrl(
                1027, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_ANIM_END", 0, 0, 1028),
        ]
    if state == 1028:
        # NA/NP immunity, 1.6/-6 bounce, back-edge turn, native AIR
        # selection and persistent-once descending animations 5050->5060
        # / 5052->5062. No new game-specific controller type required.
        raw = ", NA, NP"
        mask = (f"({no_hit_by_state_mask(raw)}) | "
                f"(({no_hit_by_attr_mask(raw)}) << 8)")
        return [
            _common_ctrl(
                1028, "IK_CNS_CTRL_NOT_HIT_BY",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, mask, 1),
            _common_ctrl(
                1028, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                q8(1.6), q8(-6),
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y | IK_CNS_CTRL_LOCAL_X",
                value4=q16(1.6), value5=q16(-6)),
            _common_ctrl(
                1028, "IK_CNS_CTRL_TURN",
                "IK_CNS_TRIGGER_STATE_ENTRY_BACK_EDGE_LT", 30),
            _common_ctrl(
                1028, "IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5052, 5050),
            _common_ctrl(
                1028, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.35),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.35)),
            _common_ctrl(
                1028, "IK_CNS_CTRL_CHANGE_ANIM_DESCENT_IF_EXISTS",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, q8(-2), 5050,
                value2=10, value3=1),
            _common_ctrl(
                1028, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    raise ValueError(f"no native ZSS lowering for state {state}")


def compile_zss_overrides(
    character_zss: Path, hits_zss: Path,
) -> dict[int, tuple[State, list[dict]]]:
    results = {}
    for path, selected in (
        (character_zss, CHARACTER_STATES),
        (hits_zss, HIT_STATES),
    ):
        source = parse_zss_states(path)
        for number in selected:
            item = source.get(number)
            if item is None:
                raise ValueError(f"{path}: missing ZSS StateDef {number}")
            observed = normalize_body(item.body)
            if observed != BODIES[number]:
                raise ValueError(
                    f"{path}: ZSS state {number} body changed or has "
                    "unsupported controllers; refusing partial conversion")
            for key, value in METADATA[number].items():
                actual = re.sub(r"\s+", "", item.metadata.get(key, "")).upper()
                if actual != value.upper():
                    raise ValueError(
                        f"{path}: state {number} {key} changed: "
                        f"{actual!r} != {value!r}")
            # The generic CNS compiler handles native StateDef metadata and
            # C emission. Controller bytecode comes only from verified ZSS.
            sd = Section(f"Statedef {number}", list(item.metadata.items()))
            results[number] = (State(number, sd, []), _controllers(number))
    return results
