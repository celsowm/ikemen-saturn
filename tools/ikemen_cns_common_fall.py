"""Lower fall states from the shared CNS common-state table."""
from __future__ import annotations


def compile_fall_state(
    n, const, state_row, deferred, q8, _common_ctrl, LOCOMOTION_STATES,
):
    """Compile one state in this group's common-state family, or return None."""
    cs = []
    row = None
    if n == 5070:
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
        # Saturn controllers have no force-feedback actuator. This
        # authored effect is an explicit platform no-op.
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
    else:
        return None
    return row, cs
