"""Lower gethit states from the shared CNS common-state table."""
from __future__ import annotations


def compile_gethit_state(
    n, const, state_row, deferred, q8, _common_ctrl, LOCOMOTION_STATES,
):
    """Compile one state in this group's common-state family, or return None."""
    cs = []
    row = None
    if n == 5000:
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
        deferred[n] = ["StateTypeSet for launch"]
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
        deferred[n] = ["StateTypeSet for launch"]
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
        # Saturn controllers have no force-feedback actuator. This
        # authored effect is an explicit platform no-op.
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
    else:
        return None
    return row, cs
