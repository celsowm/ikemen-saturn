"""Lower hit states from the shared CNS common-state table."""
from __future__ import annotations


def compile_hit_state(
    n, const, state_row, deferred, q8, _common_ctrl, LOCOMOTION_STATES,
):
    """Compile one state in this group's common-state family, or return None."""
    cs = []
    row = None
    if n == 150:
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
        # Saturn controllers have no force-feedback actuator. This
        # authored effect is an explicit platform no-op.
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
        # Saturn controllers have no force-feedback actuator. This
        # authored effect is an explicit platform no-op.
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
        # Saturn controllers have no force-feedback actuator. This
        # authored effect is an explicit platform no-op.
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
    else:
        return None
    return row, cs
