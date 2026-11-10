/* Controller family: ChangeState family, variables, guard and hit-recovery routing. */
#include "ikemen_fight_internal.h"
#include "ikemen_fight_hit_values.h"

int ikf_ctrl_apply_state(const ik_ctrl_exec_t* x) {
    ik_fight_t* fight = x->fight;
    ik_fighter_t* f = x->fighter;
    const ik_cns_controller_t* ctrl = x->ctrl;
    const ik_cns_asset_t* native_cns = x->native_cns;
    const uint16_t command_mask = x->context->command_mask;
    switch ((ik_cns_controller_type_t)ctrl->type) {
        case IK_CNS_CTRL_CHANGE_STATE: {
            const int has_ctrl = (ctrl->flags & IK_CNS_CTRL_HAS_CTRL) != 0u;
            const int16_t target = (int16_t)(ctrl->value0_expr_count
                ? ctrl->value4 / 65536 : ctrl->value0);
            ikf_turn_before_change(fight, f);
            ikf_enter_state(fight, f, target);
            if (has_ctrl) f->ctrl = (int8_t)(
                (ctrl->flags & IK_CNS_CTRL_CTRL_FROM_ROUND)
                    ? fight->round_state > 1u : ctrl->value1 != 0);
            return IKF_CTRL_END_TICK;
        }

        case IK_CNS_CTRL_CTRL_SET:
            f->ctrl = (int8_t)(ctrl->value0 != 0);
            break;

        case IK_CNS_CTRL_HIT_ADD:
            ikf_apply_hit_add(
                fight, f, ctrl->value0_expr_count
                    ? ctrl->value4 : ctrl->value0);
            break;

        case IK_CNS_CTRL_LIFE_ADD: {
            const int64_t add_q16 = ctrl->value0_expr_count
                ? ctrl->value4 : (int64_t)ctrl->value0 * 65536;
            const int32_t add = ikf_scale_life_add(
                add_q16, constants_for_fighter(fight, f),
                ikf_active_custom_defense_q16(f), ctrl->value1 != 0);
            if (add == 0) break;
            const int64_t adjusted = (int64_t)f->hp + add;
            const int max_hp = ik_fight_max_hp_player(
                fight, f->owner_player);
            int64_t hp = adjusted;
            if (hp > max_hp) hp = max_hp;
            if (hp <= 0) {
                if (ctrl->value2 == 0 && f->hp > 0) {
                    hp = 1;
                } else {
                    hp = 0;
                    const uint8_t player =
                        ikf_fighter_player_index(fight, f);
                    if (player < 2u) {
                        fight->winner = (uint8_t)((player ^ 1u) + 1u);
                        fight->events |= IK_EVENT_KO;
                        fight->win_by_ko = 1u;
                    }
                }
            }
            f->hp = (int16_t)hp;
            break;
        }

        case IK_CNS_CTRL_ATTACK_MUL_SET:
            f->attack_mul_q16 = ctrl->value0_expr_count
                ? ctrl->value4 : ctrl->value0;
            break;

        case IK_CNS_CTRL_DEFENCE_MUL_SET: {
            const int32_t value = ctrl->value0_expr_count
                ? ctrl->value4 : ctrl->value0;
            if (value <= 0) {
                f->custom_defense_q16 = INT32_MAX;
            } else {
                const int64_t inverse = (INT64_C(1) << 32) / value;
                f->custom_defense_q16 = inverse > INT32_MAX
                    ? INT32_MAX : (int32_t)inverse;
            }
            f->defense_mul_delay = (uint8_t)(ctrl->value2 != 0);
            break;
        }

        case IK_CNS_CTRL_ATTACK_DIST:
            f->attack_dist_override_q8 =
                ctrl->value0 < 0 ? 0 : ctrl->value0;
            f->has_attack_dist_override = 1u;
            break;

        case IK_CNS_CTRL_HIT_FALL_SET:
            if ((ctrl->value3 & IK_CNS_HIT_FALL_SET_VALUE) != 0) {
                f->gethit_fall = (uint8_t)(ctrl->value0 != 0);
            }
            if ((ctrl->value3 & IK_CNS_HIT_FALL_SET_X_VELOCITY) != 0) {
                f->gethit_fall_x_q8 = (int16_t)ctrl->value1;
                f->gethit_fall_x_set = 1u;
            }
            if ((ctrl->value3 & IK_CNS_HIT_FALL_SET_Y_VELOCITY) != 0) {
                f->gethit_fall_y_q8 = (int16_t)ctrl->value2;
            }
            break;

        case IK_CNS_CTRL_VAR_SET:

        case IK_CNS_CTRL_VAR_ADD: {
            ik_entity_t* entity = ikf_fighter_entity(fight, f);
            const int32_t index = ctrl->value0;
            if (entity && index >= 0 &&
                index < (int32_t)IK_ENTITY_VAR_COUNT) {
                if (ctrl->type == IK_CNS_CTRL_VAR_SET) {
                    entity->vars[index] = ctrl->value1;
                } else {
                    entity->vars[index] += ctrl->value1;
                }
            }
            break;
        }

        case IK_CNS_CTRL_SYSVAR_SET:
        case IK_CNS_CTRL_SYSVAR_ADD: {
            ik_entity_t* entity = ikf_fighter_entity(fight, f);
            const int32_t index = ctrl->value0;
            if (entity && index >= 0 &&
                index < (int32_t)IK_ENTITY_SYSVAR_COUNT) {
                if (ctrl->type == IK_CNS_CTRL_SYSVAR_SET) {
                    entity->sysvars[index] = ctrl->value1;
                } else {
                    entity->sysvars[index] += ctrl->value1;
                }
            }
            break;
        }

        case IK_CNS_CTRL_FVAR_SET:
        case IK_CNS_CTRL_FVAR_ADD: {
            ik_entity_t* entity = ikf_fighter_entity(fight, f);
            const int32_t index = ctrl->value0;
            if (entity && index >= 0 &&
                index < (int32_t)IK_ENTITY_FVAR_COUNT) {
                if (ctrl->type == IK_CNS_CTRL_FVAR_SET) {
                    entity->fvars_q16[index] = ctrl->value1;
                } else {
                    entity->fvars_q16[index] += ctrl->value1;
                }
            }
            break;
        }

        case IK_CNS_CTRL_SYSFVAR_SET:
        case IK_CNS_CTRL_SYSFVAR_ADD: {
            ik_entity_t* entity = ikf_fighter_entity(fight, f);
            const int32_t index = ctrl->value0;
            if (entity && index >= 0 &&
                index < (int32_t)IK_ENTITY_SYSFVAR_COUNT) {
                if (ctrl->type == IK_CNS_CTRL_SYSFVAR_SET) {
                    entity->sysfvars_q16[index] = ctrl->value1;
                } else {
                    entity->sysfvars_q16[index] += ctrl->value1;
                }
            }
            break;
        }

        case IK_CNS_CTRL_REMOVE_EXPLOD: {
            if (ctrl->value1 != 0 && x->index < 64u) {
                const uint64_t bit = (uint64_t)1u << x->index;
                if ((f->one_shot_controller_mask & bit) != 0u) break;
                f->one_shot_controller_mask |= bit;
            }
            (void)ik_entity_remove_explods(
                fight->entities, f->owner_player, ctrl->value0);
            break;
        }

        case IK_CNS_CTRL_SPR_PRIORITY:
            f->spr_priority = (int8_t)ctrl->value0;
            break;

        case IK_CNS_CTRL_CAPTURE_COMMAND_AXIS:
            if ((command_mask & IK_CNS_COMMAND_HOLD_BACK) != 0u) {
                f->state_axis = -1;
            } else if ((command_mask & IK_CNS_COMMAND_HOLD_FWD) != 0u) {
                f->state_axis = 1;
            }
            break;

        case IK_CNS_CTRL_GUARD_STATE_BY_TYPE: {
            int16_t target = ctrl->value0;
            if (f->guard_type == IK_CNS_STATE_CROUCH) target++;
            else if (f->guard_type == IK_CNS_STATE_AIR) target += 2;
            ikf_enter_state(fight, f, target);
            return IKF_CTRL_END_TICK;
        }

        case IK_CNS_CTRL_GUARD_END: {
            int16_t target = 0;
            if (f->guard_type == IK_CNS_STATE_CROUCH) target = 11;
            else if (f->guard_type == IK_CNS_STATE_AIR) {
                /* Upstream's hardcoded exit of state 140: crouch 11, air 51
                 * (the empty jump-down state). */
                target = ik_cns_find_state(
                    cns_for_owner(fight, f->owner_player), 51) ? 51 : 50;
            }
            ikf_enter_state(fight, f, target);
            f->ctrl = 1;
            return IKF_CTRL_END_TICK;
        }

        case IK_CNS_CTRL_HIT_RECOVER_STATE: {
            const int16_t target = f->gethit_fall ? 5050 : 5040;
            ikf_enter_state(fight, f, target);
            if (!f->gethit_fall) f->ctrl = 1;
            return IKF_CTRL_END_TICK;
        }

        case IK_CNS_CTRL_FALL_GROUND_BRANCH:
            if (f->gethit_fall_y_q8 == 0) {
                ikf_enter_state(fight, f, ctrl->value0);
                return IKF_CTRL_END_TICK;
            }
            break;

        case IK_CNS_CTRL_DOWNED_HIT_BRANCH:
            if (f->gethit_vy_q8 != 0 &&
                ik_cns_find_state(native_cns, 5030)) {
                f->anim = 5090;
                f->anim_time = 0u;
                ikf_enter_state(fight, f, 5030);
            } else if (ik_cns_find_state(native_cns, 5081)) {
                f->anim = 5080;
                f->anim_time = 0u;
                ikf_enter_state(fight, f, 5081);
            }
            return IKF_CTRL_END_TICK;

        case IK_CNS_CTRL_TURN:
            f->facing = (int8_t)-f->facing;
            break;

        case IK_CNS_CTRL_SELF_STATE:
            if (f->bound_to >= 0 && f->bound_to < 2) {
                ik_fighter_t* owner =
                    &fight->fighters[(int)f->bound_to];
                owner->target_index = -1;
                owner->target_id = -1;
            }
            ikf_release_entity_bound_fighter(fight, f);
            f->bound_to = -1;
            f->state_owner = f->owner_player;
            ikf_enter_state(fight, f, ctrl->value0);
            return IKF_CTRL_END_TICK;

        case IK_CNS_CTRL_FALL_RECOVERY: {
            const ik_cns_constants_t* c =
                constants_for_fighter(fight, f);
            if (!c ||
                (command_mask & IK_CNS_COMMAND_RECOVERY) == 0u ||
                !f->gethit_fall_recover ||
                f->fall_time < f->gethit_fall_recover_time) {
                break;
            }

            const int32_t rel_y_q8 =
                f->y_q8 -
                (int32_t)IK_FLOOR_Y * IK_CNS_Q8_ONE;
            if (f->vy_q8 > 0 &&
                rel_y_q8 >=
                    c->air_gethit_groundrecover_threshold_q8 &&
                ik_cns_find_state(native_cns, 5200)) {
                ikf_enter_state(fight, f, 5200);
                return IKF_CTRL_END_TICK;
            }
            if (f->vy_q8 >
                    c->air_gethit_airrecover_threshold_q8 &&
                ik_cns_find_state(native_cns, 5210)) {
                ikf_enter_state(fight, f, 5210);
                return IKF_CTRL_END_TICK;
            }
            break;
        }

        default:
            return IKF_CTRL_UNHANDLED;
    }
    return IKF_CTRL_NEXT;
}
