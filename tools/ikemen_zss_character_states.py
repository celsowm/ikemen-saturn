#!/usr/bin/env python3
"""Strict source-checked character-state lowering for KFM ZSS.

Only controllers already implemented by Ikemen Saturn are accepted.
Four *complete* state bodies are translated, not merely their StateDef
metadata. All other ZSS states keep the classic CNS fallback at runtime.

A source change invalidates the conversion until it has been reviewed
rather than silently introducing a behavior mismatch.
"""
from __future__ import annotations

import re
from pathlib import Path

from tools.ikemen_cns import Section, State, _common_ctrl, parse_zss_states

# Supported source bodies with every controller lowered in the exact order.
# Normalization discards insignificant spacing and ZSS '#' comments, but no
# executable token: any new controller causes a hard failure.
BODIES = {
    170: "nothitby{value:sca;time:1}",
    180: "changestate{value:181;ctrl:0}",
    820: ("iftime=0{changeanim2{value:820}}"
          "if!gethitvar(isbound){selfstate{value:5050}}"),
    1025: ("changeanim2{value:1025}"
           "ifhitshakeover=1{changestate{value:1026}}"),
}

CHARACTER_STATES = (170, 180)
HIT_STATES = (820, 1025)

# These guards protect against silently compiling outdated states with an
# incompatible move class, physics type or action.
METADATA = {
    170: {"type": "S", "movetype": "I", "physics": "S", "anim": "170", "ctrl": "0"},
    180: {"type": "S", "movetype": "I", "physics": "S", "anim": "-2", "ctrl": "0"},
    820: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
    1025: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
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
