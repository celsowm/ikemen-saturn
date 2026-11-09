"""Lower guard states from the shared CNS common-state table."""
from __future__ import annotations


def compile_guard_state(
    n, const, state_row, deferred, q8, _common_ctrl, LOCOMOTION_STATES,
):
    """Compile one state in this group's common-state family, or return None."""
    cs = []
    row = None
    if n == 120:
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
    else:
        return None
    return row, cs
