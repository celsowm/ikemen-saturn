"""Lower motion states from the shared CNS common-state table."""
from __future__ import annotations


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


def locomotion_ctrl_rows(
    number: int, const: dict[str, int], controller_factory,
) -> list[dict]:
    """Controller rows for the walk (20) and run (100) locomotion states.

    Shared by the common1 compilation and the source-checked ZSS overrides so
    both paths emit identical rows; the ZSS bodies differ from common1 only by
    AI-only guards, which stay inert for the human path.
    """
    if number == 20:
        return [
            controller_factory(
                20, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                "IK_CNS_COMMAND_HOLD_BACK", 0,
                const["walk_back_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            controller_factory(
                20, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_COMMAND_ACTIVE",
                "IK_CNS_COMMAND_HOLD_FWD", 0,
                const["walk_fwd_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            controller_factory(
                20, "IK_CNS_CTRL_CHANGE_ANIM_BY_VX",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, -1, 20,
            ),
        ]
    if number == 100:
        return [
            controller_factory(
                100, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0,
                const["run_fwd_x_q8"], 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_LOCAL_X",
            ),
            controller_factory(
                100, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_COMMAND_INACTIVE",
                "IK_CNS_COMMAND_HOLD_FWD", 0, 0, 0,
            ),
        ]
    raise ValueError(f"state {number}: no shared locomotion controller lowering")


def compile_motion_state(
    n, const, state_row, deferred, q8, _common_ctrl, LOCOMOTION_STATES,
):
    """Compile one state in this group's common-state family, or return None."""
    cs = []
    row = None
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
        cs += locomotion_ctrl_rows(n, const, _common_ctrl)
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
    else:
        return None
    return row, cs
