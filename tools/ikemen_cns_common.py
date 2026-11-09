"""Lower shared common-state definitions into the CNS runtime tables."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    from .ikemen_text import read_mugen_text
except ImportError:  # direct converter-script invocation
    from ikemen_text import read_mugen_text

Q8 = 256


def number(text: str | None, default: float = 0.0) -> float:
    if text is None:
        return default
    value = text.strip()
    if value[:1].casefold() == "s":
        value = value[1:]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise ValueError(f"expected numeric literal, got {text!r}")
    return float(value)


def integer(text: str | None, default: int = 0) -> int:
    value = number(text, float(default))
    if int(value) != value:
        raise ValueError(f"expected integer literal, got {text!r}")
    return int(value)


def q8(value: float, wide: bool = False) -> int:
    result = int(round(value * Q8))
    low, high = (-(1 << 31), (1 << 31) - 1) if wide else (-32768, 32767)
    if not low <= result <= high:
        raise ValueError(f"Q8.8 overflow for {value}")
    return result


@dataclass
class ZssState:
    number: int
    metadata: dict[str, str]
    body: str


def parse_zss_states(path: Path) -> dict[int, ZssState]:
    text = read_mugen_text(path)
    # Support both ZSS ([StateDef N;...]) and CNS ([Statedef N]) formats
    matches = list(re.finditer(
        r"\[(?:StateDef|Statedef)\s+(-?\d+)(?:\s*;([^\]]*))?\]",
        text,
        flags=re.I,
    ))
    states: dict[int, ZssState] = {}
    for i, match in enumerate(matches):
        number_ = int(match.group(1))
        meta: dict[str, str] = {}
        metadata_text = (match.group(2) or "").strip()
        metadata_text = "\n".join(line.split("#", 1)[0]
                                  for line in metadata_text.splitlines())
        for part in metadata_text.split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            key, value = part.split(":", 1)
            meta[key.strip().lower()] = value.strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        states[number_] = ZssState(number_, meta, text[match.end():end])
    return states


def _common_ctrl(
    state_no: int,
    ctype: str,
    trigger_kind: str = "IK_CNS_TRIGGER_ALWAYS",
    trigger_value: int | str = 0,
    trigger_value2: int | str = 0,
    value0: int | str = 0,
    value1: int | str = 0,
    flags: str = "0u",
    value2: int | str = 0,
    value3: int | str = 0,
    value4: int | str = 0,
    value5: int | str = 0,
    value6: int | str = 0,
    value7: int | str = 0,
) -> dict:
    return {
        "state_number": state_no,
        "type": ctype,
        "trigger_kind": trigger_kind,
        "trigger_value": trigger_value,
        "trigger_value2": trigger_value2,
        "value0": value0,
        "value1": value1,
        "flags": flags,
        "value2": value2,
        "value3": value3,
        "value4": value4,
        "value5": value5,
        "value6": value6,
        "value7": value7,
    }


LOCOMOTION_STATES = (20, 100)


def locomotion_row_patch(number: int) -> dict:
    """State-row overrides for the shared walk/run lowering.

    States 20 and 100 omit movetype and ctrl in every KFM StateDef; upstream
    carries the previous values over on entry. The Saturn runtime stores
    control as a static per-state value, so the verified lowering pins
    ctrl = 1 (walk and run always stay controllable) and movetype = idle
    (their only entry paths are control-owning movement states). State 100
    additionally asserts NoWalk/NoAutoTurn, which the runtime models as the
    state's static assert flags.
    """
    if number == 20:
        return {"move_type": "IK_CNS_MOVE_IDLE", "ctrl": 1}
    if number == 100:
        return {
            "move_type": "IK_CNS_MOVE_IDLE",
            "ctrl": 1,
            "assert_special_flags": (
                "IK_CNS_STATE_ASSERT_NO_WALK | "
                "IK_CNS_STATE_ASSERT_NO_AUTO_TURN"
            ),
        }
    raise ValueError(f"state {number}: no shared locomotion row patch")


def locomotion_ctrl_rows(number: int, const: dict[str, int]) -> list[dict]:
    """Controller rows for the walk (20) and run (100) locomotion states.

    Shared by the common1 compilation and the source-checked ZSS overrides so
    both paths emit identical rows; the ZSS bodies differ from common1 only by
    AI-only guards, which stay inert for the human path.
    """
    if number == 20:
        return [
            _common_ctrl(
                20, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                "IK_CNS_COMMAND_HOLD_BACK", 0,
                const["walk_back_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            _common_ctrl(
                20, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                "IK_CNS_COMMAND_HOLD_FWD", 0,
                const["walk_fwd_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            _common_ctrl(
                20, "IK_CNS_CTRL_CHANGE_ANIM_BY_VX",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, -1, 20,
            ),
        ]
    if number == 100:
        return [
            _common_ctrl(
                100, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0,
                const["run_fwd_x_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            _common_ctrl(
                100, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_COMMAND_INACTIVE",
                "IK_CNS_COMMAND_HOLD_FWD", 0, 0, 0,
            ),
        ]
    raise ValueError(f"state {number}: no shared locomotion controller lowering")


def compile_common_states(
    path: Path,
    selected: list[int],
    const: dict[str, int],
    controller_ofs: int,
    state_type_codes: dict[str, str],
    move_type_codes: dict[str, str],
    physics_codes: dict[str, str],
) -> tuple[list[dict], list[dict], dict[int, list[str]]]:
    """Lower the first common1.zss locomotion subset to generic CNS ops.

    This is deliberately strict: only states whose ZSS semantics have an
    explicit lowering below are accepted. Source-state presence is verified,
    and deferred presentation-only behavior is surfaced in the JSON report.
    """
    source = parse_zss_states(path)
    missing = [n for n in selected if n not in source]
    if missing:
        raise ValueError(f"missing common Statedef(s): {missing}")

    supported = {
        0, 10, 11, 12, 20, 40, 45, 50, 51, 52, 100, 105, 106,
        120, 130, 131, 132, 140, 150, 151, 152, 153, 154, 155, 175,
        5000, 5001, 5010, 5011, 5020, 5030, 5035, 5040, 5050,
        5070, 5071, 5080, 5081, 5100, 5101, 5110, 5120, 5150,
        5200, 5201, 5210,
    }
    unsupported = sorted(set(selected) - supported)
    if unsupported:
        raise ValueError(
            "common1 states do not have a Saturn lowering yet: "
            f"{unsupported}"
        )

    def meta(n: int, key: str, default: str) -> str:
        return source[n].metadata.get(key, default).strip().upper()

    def state_row(
        n: int,
        anim: int,
        ctrl: int,
        land_state: int = 0,
        spr: int | None = None,
    ) -> dict:
        stype = state_type_codes.get(meta(n, "type", "U"))
        physics_value = physics_codes.get(meta(n, "physics", "N"))
        if stype is None or physics_value is None:
            raise ValueError(f"common state {n}: unsupported StateDef metadata")
        priority = (
            integer(source[n].metadata.get("sprpriority"), 0)
            if spr is None else spr
        )
        move_type_value = move_type_codes.get(meta(n, "movetype", "I"))
        if move_type_value is None:
            raise ValueError(f"common state {n}: unsupported move type")
        return {
            "number": n,
            "anim": anim,
            "power_add": 0,
        "power_add_expr": None,
        "juggle_expr": None,
            "velset_x_q8": 0,
            "velset_y_q8": 0,
            "state_type": stype,
            "move_type": move_type_value,
            "physics": physics_value,
            "ctrl": ctrl,
            "spr_priority": priority,
            "has_velset": 0,
            "hitdef_ofs": 0,
            "hitdef_count": 0,
            "playsnd_ofs": 0,
            "playsnd_count": 0,
            "controller_ofs": 0,
            "controller_count": 0,
            "land_state": land_state,
            "air_accel_q8": 0,
            "land_level_q8": 0,
            "air_motion_start": 0,
            "land_ctrl": 0,
            "juggle": 0,
            "has_juggle": 0,
            "owns_air_accel": 0,
            "assert_special_flags": "0u",
            "unsupported_controllers": [],
        }

    rows: list[dict] = []
    controllers: list[dict] = []
    deferred: dict[int, list[str]] = {}

    for n in selected:
        begin = controller_ofs + len(controllers)
        cs: list[dict] = []
        row: dict

        if n == 0:
            # Upstream state 0 has no anim: it keeps the turn anim (5) until
            # it ends and snaps any other anim to 0 on its first tick.
            row = state_row(0, -1, 1)
            cs += [
                _common_ctrl(
                    0, "IK_CNS_CTRL_IDLE_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                ),
                _common_ctrl(
                    0, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 4, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    0, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["stand_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    0, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_NOT_ALIVE", 0, 0, 5050, 0,
                ),
            ]

        elif n == 10:
            row = state_row(10, 10, -1)
            cs += [
                _common_ctrl(
                    10, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, q8(.75), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    10, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["crouch_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    10, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 11, 0,
                ),
            ]

        elif n == 11:
            row = state_row(11, 11, 1)
            cs += [
                _common_ctrl(
                    11, "IK_CNS_CTRL_CHANGE_ANIM_IF_END_FROM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 6, 11,
                ),
                _common_ctrl(
                    11, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["crouch_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
            ]

        elif n == 12:
            row = state_row(12, 12, -1)
            cs.append(_common_ctrl(
                12, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_ANIM_END", 0, 0, 0, 0,
            ))

        elif n in LOCOMOTION_STATES:
            row = state_row(n, -1 if n == 20 else 100, 1)
            row.update(locomotion_row_patch(n))
            cs += locomotion_ctrl_rows(n, const)

        elif n == 40:
            row = state_row(40, 40, 0, spr=1)
            cs += [
                _common_ctrl(
                    40, "IK_CNS_CTRL_CAPTURE_COMMAND_AXIS",
                    "IK_CNS_TRIGGER_ALWAYS",
                ),
                _common_ctrl(
                    40, "IK_CNS_CTRL_JUMP_LAUNCH",
                    "IK_CNS_TRIGGER_ANIM_END",
                ),
                _common_ctrl(
                    40, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 50, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        elif n == 45:
            row = state_row(45, 41, 0)
            row["has_velset"] = 1
            row["owns_air_accel"] = 1   # physics N: nothing accelerates it
            cs += [
                _common_ctrl(
                    45, "IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 44, 41,
                ),
                _common_ctrl(
                    45, "IK_CNS_CTRL_CAPTURE_COMMAND_AXIS",
                    "IK_CNS_TRIGGER_ALWAYS",
                ),
                _common_ctrl(
                    45, "IK_CNS_CTRL_AIR_JUMP_LAUNCH",
                    "IK_CNS_TRIGGER_TIME_EQ", 2,
                ),
                _common_ctrl(
                    45, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_TIME_EQ", 2, 0, 50, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        elif n == 50:
            row = state_row(50, -1, -1, land_state=52)
            cs += [
                _common_ctrl(
                    50, "IK_CNS_CTRL_CHANGE_ANIM_BY_VX",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 41, 42,
                ),
                _common_ctrl(
                    50, "IK_CNS_CTRL_CHANGE_ANIM_DESCENT_IF_EXISTS",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, q8(-2), 41,
                ),
            ]

        elif n == 51:
            row = state_row(51, -1, -1, land_state=52)

        elif n == 52:
            row = state_row(52, 47, 0)
            cs += [
                _common_ctrl(
                    52, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    52, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    52, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 3, 0, 1, 0,
                ),
                _common_ctrl(
                    52, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["stand_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    52, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 0, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        elif n == 105:
            row = state_row(105, 105, 0, land_state=106)
            row["land_before_move"] = 1
            cs += [
                _common_ctrl(
                    105, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                    const["run_back_x_q8"], const["run_back_y_q8"],
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y | "
                    "IK_CNS_CTRL_LOCAL_X",
                ),
                _common_ctrl(
                    105, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 2, 0, 1, 0,
                ),
            ]

        elif n == 120:
            row = state_row(120, -1, -1)
            cs += [
                _common_ctrl(
                    120, "IK_CNS_CTRL_GUARD_ANIM_BY_TYPE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 120, 0,
                ),
                _common_ctrl(
                    120, "IK_CNS_CTRL_GUARD_STATE_BY_TYPE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 130, 0,
                ),
                _common_ctrl(
                    120, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_GUARD_RELEASE", 0, 0, 140, 0,
                ),
            ]

        elif n == 130:
            row = state_row(130, 130, -1)
            cs += [
                _common_ctrl(
                    130, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                    "IK_CNS_COMMAND_HOLD_DOWN", 0, 131, 0,
                ),
                _common_ctrl(
                    130, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_GUARD_RELEASE", 0, 0, 140, 0,
                ),
            ]

        elif n == 131:
            row = state_row(131, 131, -1)
            cs += [
                _common_ctrl(
                    131, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_COMMAND_INACTIVE",
                    "IK_CNS_COMMAND_HOLD_DOWN", 0, 130, 0,
                ),
                _common_ctrl(
                    131, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_GUARD_RELEASE", 0, 0, 140, 0,
                ),
            ]

        elif n == 132:
            row = state_row(132, 132, -1, land_state=52)
            row["air_accel_q8"] = const["yaccel_q8"]   # IkSys_AirGuardLand VelAdd
            row["air_accel_q16"] = const["yaccel_q16"]
            cs.append(_common_ctrl(
                132, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_GUARD_RELEASE", 0, 0, 140, 0,
            ))

        elif n == 140:
            row = state_row(140, -1, 1)
            cs += [
                _common_ctrl(
                    140, "IK_CNS_CTRL_GUARD_ANIM_BY_TYPE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 140, 0,
                ),
                _common_ctrl(
                    140, "IK_CNS_CTRL_GUARD_END",
                    "IK_CNS_TRIGGER_ANIM_END",
                ),
            ]

        elif n == 150:
            row = state_row(150, 150, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    150, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 151, 0,
                ),
                _common_ctrl(
                    150, "IK_CNS_CTRL_CHANGE_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 150, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback"]

        elif n == 151:
            row = state_row(151, 150, -1)
            cs += [
                _common_ctrl(
                    151, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    151, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_HIT_SLIDE_TIME", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    151, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_HIT_CTRL_TIME", 0, 0, 1, 0,
                ),
                _common_ctrl(
                    151, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 130, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        elif n == 152:
            row = state_row(152, 151, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    152, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 153, 0,
                ),
                _common_ctrl(
                    152, "IK_CNS_CTRL_CHANGE_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 151, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback"]

        elif n == 153:
            row = state_row(153, 151, -1)
            cs += [
                _common_ctrl(
                    153, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    153, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_HIT_SLIDE_TIME", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    153, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_HIT_CTRL_TIME", 0, 0, 1, 0,
                ),
                _common_ctrl(
                    153, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 131, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        elif n == 154:
            row = state_row(154, 152, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    154, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 155, 0,
                ),
                _common_ctrl(
                    154, "IK_CNS_CTRL_CHANGE_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 152, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback"]

        elif n == 155:
            row = state_row(155, 152, -1, land_state=52)
            row["air_accel_q8"] = const["yaccel_q8"]   # IkSys_AirGuardLand VelAdd
            row["air_accel_q16"] = const["yaccel_q16"]
            cs += [
                _common_ctrl(
                    155, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    155, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_HIT_CTRL_TIME", 0, 0, 1, 0,
                ),
            ]

        elif n == 175:
            # common1.zss draw state. KFM has no Anim 175, so upstream
            # immediately falls back to State 170 (lose/draw presentation),
            # whose authored animation is 170.
            row = state_row(175, -1, 0)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    175, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 170, 0,
                ),
            ]

        elif n == 5000:
            row = state_row(5000, -1, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    5000, "IK_CNS_CTRL_GET_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                ),
                _common_ctrl(
                    5000, "IK_CNS_CTRL_STATE_TYPE_SET",
                    "IK_CNS_TRIGGER_HIT_LAUNCH_ENTRY", 0, 0,
                    "IK_CNS_STATE_AIR", 0,
                ),
                _common_ctrl(
                    5000, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_LAUNCH", 0, 0, 5030, 0,
                ),
                _common_ctrl(
                    5000, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_NO_LAUNCH", 0, 0, 5001, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback", "StateTypeSet for launch"]

        elif n == 5001:
            row = state_row(5001, -1, -1)
            cs += [
                _common_ctrl(
                    5001, "IK_CNS_CTRL_GET_HIT_ANIM",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 3, 0,
                ),
                _common_ctrl(
                    5001, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5001, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_HIT_SLIDE_GE", 0, 0, q8(.6), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5001, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 0, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]
            deferred[n] = ["DefenceMulSet"]

        elif n == 5010:
            row = state_row(5010, -1, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    5010, "IK_CNS_CTRL_GET_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 1, 0,
                ),
                _common_ctrl(
                    5010, "IK_CNS_CTRL_STATE_TYPE_SET",
                    "IK_CNS_TRIGGER_HIT_LAUNCH_ENTRY", 0, 0,
                    "IK_CNS_STATE_AIR", 0,
                ),
                _common_ctrl(
                    5010, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_LAUNCH", 0, 0, 5030, 0,
                ),
                _common_ctrl(
                    5010, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_NO_LAUNCH", 0, 0, 5011, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback", "StateTypeSet for launch"]

        elif n == 5011:
            row = state_row(5011, -1, -1)
            cs += [
                _common_ctrl(
                    5011, "IK_CNS_CTRL_GET_HIT_ANIM",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 4, 0,
                ),
                _common_ctrl(
                    5011, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5011, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_HIT_SLIDE_GE", 0, 0, q8(.6), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5011, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 11, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]
            deferred[n] = ["DefenceMulSet"]

        elif n == 5020:
            row = state_row(5020, -1, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    5020, "IK_CNS_CTRL_GET_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 2, 0,
                ),
                _common_ctrl(
                    5020, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 5030, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback"]

        elif n == 5030:
            row = state_row(5030, -1, 0)
            row["land_level_q8"] = const["air_gethit_groundlevel_q8"]
            cs += [
                _common_ctrl(
                    5030, "IK_CNS_CTRL_AIR_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5030, 0,
                ),
                _common_ctrl(
                    5030, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5030, "IK_CNS_CTRL_HIT_RECOVER_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER",
                ),
                _common_ctrl(
                    5030, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 5035, 0,
                ),
            ]
            deferred[n] = ["selfAnimExist 5030"]

        elif n == 5035:
            row = state_row(5035, -1, -1)
            row["land_level_q8"] = const["air_gethit_groundlevel_q8"]
            cs += [
                _common_ctrl(
                    5035, "IK_CNS_CTRL_AIR_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5035, 1,
                ),
                _common_ctrl(
                    5035, "IK_CNS_CTRL_HIT_RECOVER_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER",
                ),
                _common_ctrl(
                    5035, "IK_CNS_CTRL_HIT_RECOVER_STATE",
                    "IK_CNS_TRIGGER_ANIM_END",
                ),
            ]

        elif n == 5040:
            row = state_row(5040, -1, 1, land_state=52)
            cs += [
                _common_ctrl(
                    5040, "IK_CNS_CTRL_LAND_HIT_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5040, 0,
                ),
                _common_ctrl(
                    5040, "IK_CNS_CTRL_MOVE_TYPE_SET",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, "IK_CNS_MOVE_IDLE", 0,
                ),
            ]
            deferred[n] = ["alive=false -> 5050"]

        elif n == 5050:
            row = state_row(5050, -1, 0, land_state=5100)
            row["land_level_q8"] = const["air_gethit_groundlevel_q8"]
            cs += [
                _common_ctrl(
                    5050, "IK_CNS_CTRL_FALL_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS",
                ),
                _common_ctrl(
                    5050, "IK_CNS_CTRL_FALL_RECOVERY",
                    "IK_CNS_TRIGGER_ALWAYS",
                ),
            ]

        elif n == 5070:
            row = state_row(5070, 5070, -1)
            row["has_velset"] = 1
            cs += [
                _common_ctrl(
                    5070, "IK_CNS_CTRL_RESTART_ANIM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5070, 0,
                ),
                _common_ctrl(
                    5070, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 5071, 0,
                ),
            ]
            deferred[n] = ["ForceFeedback"]

        elif n == 5071:
            row = state_row(5071, -1, -1, land_state=5110)
            row["land_level_q8"] = const["air_gethit_trip_groundlevel_q8"]
            cs.append(_common_ctrl(
                5071, "IK_CNS_CTRL_HIT_VEL_SET",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
            ))

        elif n == 5080:
            row = state_row(5080, -1, -1)
            row["has_velset"] = 1
            cs.append(_common_ctrl(
                5080, "IK_CNS_CTRL_DOWNED_HIT_BRANCH",
                "IK_CNS_TRIGGER_TIME_EQ", 0,
            ))

        elif n == 5081:
            row = state_row(5081, -1, -1)
            cs += [
                _common_ctrl(
                    5081, "IK_CNS_CTRL_HIT_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5081, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5081, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_HIT_OVER", 0, 0, 5110, 0,
                ),
            ]

        elif n == 5100:
            row = state_row(5100, -1, -1)
            cs += [
                _common_ctrl(
                    5100, "IK_CNS_CTRL_ANIM_ADD_MOD10",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5100, 0,
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, q8(.75), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_FALL_ENV_SHAKE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0,
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_MAKE_DUST",
                    "IK_CNS_TRIGGER_TIME_EQ", 1, 0, 60, 0,
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_FALL_GROUND_BRANCH",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5110, 0,
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_HIT_FALL_DAMAGE",
                    "IK_CNS_TRIGGER_TIME_EQ", 3,
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_POS_FREEZE",
                    flags="IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5100, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 5101, 0,
                ),
            ]
            deferred.pop(n, None)

        elif n == 5101:
            row = state_row(5101, -1, -1)
            row["owns_air_accel"] = 1   # VelAdd below, like upstream
            cs += [
                _common_ctrl(
                    5101, "IK_CNS_CTRL_ANIM_ADD_MOD10",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5160, 1,
                ),
                _common_ctrl(
                    5101, "IK_CNS_CTRL_FALL_BOUNCE_VEL",
                    "IK_CNS_TRIGGER_TIME_EQ", 0,
                ),
                _common_ctrl(
                    5101, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0,
                    const["down_bounce_offset_y_q8"],
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5101, "IK_CNS_CTRL_POS_ADD",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                    const["down_bounce_offset_x_q8"], 0,
                ),
                _common_ctrl(
                    5101, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_TIME_GE", 1, 0, 0,
                    const["down_bounce_yaccel_q8"],
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                # Upstream lands through a controller, so the new state runs
                # on the tick after the position crossed the ground level.
                _common_ctrl(
                    5101, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL",
                    const["down_bounce_groundlevel_q8"], 0, 5110, 0,
                ),
            ]

        elif n == 5110:
            row = state_row(5110, 5110, -1)
            cs += [
                _common_ctrl(
                    5110, "IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5170, 5110,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_CHANGE_ANIM_IF_END_FROM",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5170, 5110,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_FALL_ENV_SHAKE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_HIT_FALL_DAMAGE",
                    "IK_CNS_TRIGGER_TIME_EQ", 0,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_MAKE_DUST",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 60, 0,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, q8(.85), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["down_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_POS_ADD_VEL",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_DEFEATED_LIEDOWN_READY",
                    0, 0, 5150, 0,
                ),
                _common_ctrl(
                    5110, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_TIME_EQ", const["liedown_time"],
                    0, 5120, 0,
                ),
            ]
            deferred[n] = ["FallEnvShake", "HitFallDamage"]

        elif n == 5120:
            row = state_row(5120, 5120, -1)
            cs += [
                _common_ctrl(
                    5120, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5120, "IK_CNS_CTRL_NOT_HIT_BY",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 7, 1,
                ),
                _common_ctrl(
                    5120, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_ANIM_END", 0, 0, 0, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]
            deferred[n] = ["HitFallSet and post-get-up attribute windows"]

        elif n == 5150:
            # Upstream common1 does not declare an anim on StateDef 5150.
            # Preserve the incoming liedown animation; its Time=0 controllers
            # decide whether a 514x defeated variant actually exists.
            row = state_row(5150, -1, 0, spr=-3)
            cs += [
                _common_ctrl(
                    5150, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, q8(.85), 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5150, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["down_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5150, "IK_CNS_CTRL_POS_ADD_VEL",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    5150, "IK_CNS_CTRL_NOT_HIT_BY",
                    "IK_CNS_TRIGGER_ALWAYS", 0, 0, 7, 1,
                ),
            ]
            deferred.pop(n, None)

        elif n == 5200:
            row = state_row(5200, -1, -1, land_state=5201)
            row["land_level_q8"] = const[
                "air_gethit_groundrecover_groundlevel_q8"
            ]
            cs.append(_common_ctrl(
                5200, "IK_CNS_CTRL_CHANGE_ANIM_IF_END_FROM",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 5035, 5050,
            ))

        elif n == 5201:
            row = state_row(5201, 5200, -1, land_state=52)
            cs += [
                _common_ctrl(
                    5201, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                    const["air_gethit_groundrecover_x_q8"],
                    const["air_gethit_groundrecover_y_q8"],
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y | "
                    "IK_CNS_CTRL_LOCAL_X",
                ),
                _common_ctrl(
                    5201, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
            ]
            deferred[n] = ["Turn by P2Dist", "PalFX", "Explod", "NotHitBy"]

        elif n == 5210:
            row = state_row(5210, 5210, 0, land_state=52)
            row["land_ctrl"] = 1
            row["air_accel_q8"] = const["air_gethit_airrecover_yaccel_q8"]
            row["air_accel_q16"] = const["air_gethit_airrecover_yaccel_q16"]
            row["air_motion_start"] = 4
            palfx_mul_identity = 256 | (256 << 9) | (256 << 18)
            cs += [
                _common_ctrl(
                    5210, "IK_CNS_CTRL_PAL_FX",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                    3, 128 | (128 << 9) | (128 << 18),
                    "0u", 0, 1, palfx_mul_identity, 0, 1,
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_TURN",
                    "IK_CNS_TRIGGER_P2_DIST_X_LT_Q8_AT_TIME",
                    q8(-20), 1,
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_NOT_HIT_BY",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                    7, 15,
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_MUL",
                    "IK_CNS_TRIGGER_TIME_EQ", 4, 0,
                    const["air_gethit_airrecover_mul_x_q8"],
                    const["air_gethit_airrecover_mul_y_q8"],
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_TIME_EQ", 4, 0,
                    const["air_gethit_airrecover_add_x_q8"],
                    const["air_gethit_airrecover_add_y_q8"],
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                    "IK_CNS_COMMAND_HOLD_UP", 0, 0,
                    const["air_gethit_airrecover_up_q8"],
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                    "IK_CNS_COMMAND_HOLD_DOWN", 0, 0,
                    const["air_gethit_airrecover_down_q8"],
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                    "IK_CNS_COMMAND_HOLD_FWD", 0,
                    const["air_gethit_airrecover_fwd_q8"], 0,
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_VEL_ADD",
                    "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                    "IK_CNS_COMMAND_HOLD_BACK", 0,
                    const["air_gethit_airrecover_back_q8"], 0,
                    "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
                ),
                _common_ctrl(
                    5210, "IK_CNS_CTRL_CTRL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 20, 0, 1, 0,
                ),
            ]

        elif n == 106:
            row = state_row(106, 47, 0)
            cs += [
                _common_ctrl(
                    106, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_ABS_VX_LT_Q8",
                    const["stand_friction_threshold_q8"], 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_X",
                ),
                _common_ctrl(
                    106, "IK_CNS_CTRL_VEL_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    106, "IK_CNS_CTRL_POS_SET",
                    "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                    "IK_CNS_CTRL_AXIS_Y",
                ),
                _common_ctrl(
                    106, "IK_CNS_CTRL_MAKE_DUST",
                    "IK_CNS_TRIGGER_TIME_EQ", 2, 0, 0, 0,
                ),
                _common_ctrl(
                    106, "IK_CNS_CTRL_CHANGE_STATE",
                    "IK_CNS_TRIGGER_TIME_EQ", 7, 0, 0, 1,
                    "IK_CNS_CTRL_HAS_CTRL",
                ),
            ]

        row["controller_ofs"] = begin
        row["controller_count"] = len(cs)
        rows.append(row)
        controllers.extend(cs)

    return rows, controllers, deferred

