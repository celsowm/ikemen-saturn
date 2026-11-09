/* Applying resolved guard and throw contacts from a root fighter. */
#include "ikemen_fight_internal.h"
#include "ikemen_fight_hit_values.h"

void ikf_record_hit(ik_fighter_t* attacker, uint8_t target_player) {
    if (!attacker) return;
    attacker->move_hit = 1u;
    if (attacker->hit_count < UINT16_MAX) ++attacker->hit_count;
    if (target_player < 2u) {
        const uint8_t target_bit = (uint8_t)(1u << target_player);
        if (!(attacker->uniq_hit_mask & target_bit)) {
            attacker->uniq_hit_mask |= target_bit;
            if (attacker->uniq_hit_count < UINT16_MAX) {
                ++attacker->uniq_hit_count;
            }
        }
    }
}

void ikf_record_received_hit(ik_fighter_t* victim) {
    if (!victim) return;
    if (victim->hitstun == 0u) {
        victim->gethit_hit_count = 1u;
    } else if (victim->gethit_hit_count < UINT16_MAX) {
        ++victim->gethit_hit_count;
    }
}

void ikf_release_bound_target(ik_fight_t* fight, int owner) {
    if (!fight || owner < 0 || owner > 1) return;
    ik_fighter_t* f = &fight->fighters[owner];
    if (f->target_index < 0 || f->target_index > 1) return;
    ik_fighter_t* target = &fight->fighters[(int)f->target_index];
    if (target->bound_to == owner) {
        target->bound_to = -1;
        target->bound_entity = ik_entity_invalid_handle();
    }
    f->target_index = -1;
    f->target_id = -1;
}

/* A fighter that leaves MoveType H stops being anyone's target, forgets who
 * juggled it and is released from any bind (upstream exitTarget). */
void ikf_exit_target(ik_fight_t* fight, ik_fighter_t* f) {
    const uint8_t self = ikf_fighter_player_index(fight, f);
    f->juggle_owner = -1;
    if (f->bound_to >= 0) {
        f->bound_to = -1;
        f->bound_entity = ik_entity_invalid_handle();
    }
    if (self < 2u) {
        ik_fighter_t* other = &fight->fighters[self ^ 1u];
        if (other->target_index == (int8_t)self) {
            other->target_index = -1;
            other->target_id = -1;
        }
    }
}

void ikf_release_entity_bound_fighter(
    ik_fight_t* fight,
    ik_fighter_t* fighter
) {
    if (!fight || !fighter ||
        !ik_entity_handle_is_valid(fighter->bound_entity)) {
        return;
    }
    if (fight->entities) {
        const ik_entity_t* source =
            ik_entity_get_const(
                fight->entities, fighter->bound_entity);
        if (source) {
            const uint8_t player =
                ikf_fighter_player_index(fight, fighter);
            if (player < 2u) {
                (void)ik_entity_remove_target(
                    fight->entities, fighter->bound_entity,
                    fight->player_entities[player]);
            }
        }
    }
    fighter->bound_entity = ik_entity_invalid_handle();
}

void ikf_apply_guard(ik_fight_t* fight, int victim,
                        const ik_fight_controls_t* controls,
                        const ik_cns_hitdef_t* hitdef) {
    if (!fight || !controls || !hitdef || victim < 0 || victim > 1) return;
    ik_fighter_t* v = &fight->fighters[victim];
    ik_fighter_t* a = &fight->fighters[victim ^ 1];
    ik_cns_hitdef_t evaluated_hitdef;
    if (hitdef->guard_hit_time_expr_count ||
                   hitdef->guard_slide_time_expr_count ||
                   hitdef->guard_ctrl_time_expr_count ||
                   hitdef->guard_damage_expr_count ||
                   hitdef->pause_p1_expr_count ||
                   hitdef->pause_p2_expr_count ||
                   hitdef->fall_x_velocity_expr_count ||
                   hitdef->fall_y_velocity_expr_count ||
                   hitdef->guard_velocity_x_expr_count) {
        evaluated_hitdef = *hitdef;
        const ik_cns_asset_t* cns = cns_for_fighter(fight, a);
        evaluated_hitdef.guard_hit_time = eval_fighter_time_expr(
            fight, a, cns, hitdef->guard_hit_time_expr_ofs,
            hitdef->guard_hit_time_expr_count, hitdef->guard_hit_time);
        evaluated_hitdef.guard_slide_time = eval_fighter_time_expr(
            fight, a, cns, hitdef->guard_slide_time_expr_ofs,
            hitdef->guard_slide_time_expr_count, hitdef->guard_slide_time);
        evaluated_hitdef.guard_ctrl_time = eval_fighter_time_expr(
            fight, a, cns, hitdef->guard_ctrl_time_expr_ofs,
            hitdef->guard_ctrl_time_expr_count, hitdef->guard_ctrl_time);
        evaluated_hitdef.guard_damage = eval_fighter_damage_expr(
            fight, a, cns, hitdef->guard_damage_expr_ofs,
            hitdef->guard_damage_expr_count, hitdef->guard_damage);
        evaluated_hitdef.pause_p1 = eval_fighter_time_expr(
            fight, a, cns, hitdef->pause_p1_expr_ofs,
            hitdef->pause_p1_expr_count, hitdef->pause_p1);
        evaluated_hitdef.pause_p2 = eval_fighter_time_expr(
            fight, a, cns, hitdef->pause_p2_expr_ofs,
            hitdef->pause_p2_expr_count, hitdef->pause_p2);
        evaluated_hitdef.guard_velocity_x_q8 = eval_fighter_q8_expr(
            fight, a, cns, hitdef->guard_velocity_x_expr_ofs,
            hitdef->guard_velocity_x_expr_count,
            hitdef->guard_velocity_x_q8);
        hitdef = &evaluated_hitdef;
    }
    const uint8_t type = ikf_guard_type_for(fight, v, controls);

    int guard_ko = 0;
    if (hitdef->guard_damage > 0) {
        v->hp = (int16_t)(v->hp - hitdef->guard_damage);
        if (v->hp <= 0) {
            if (hitdef->guard_kill &&
                (v->assert_controller_flags & IK_CNS_ASSERT_NO_KO) == 0u &&
                (fight->global_assert_controller_flags &
                 IK_CNS_GLOBAL_ASSERT_NO_KO) == 0u) {
                v->hp = 0;
                guard_ko = 1;
            } else {
                v->hp = 1;
            }
        }
    }

    v->hit_shake_time = hitdef->pause_p2;
    a->hit_pause = hitdef->pause_p1;
    v->hitstun = hitdef->guard_hit_time;
    v->hit_slide_time = hitdef->guard_slide_time;
    v->hit_ctrl_time = hitdef->guard_ctrl_time;
    v->guard_type = type;

    if (type == IK_CNS_STATE_AIR) {
        v->gethit_vx_q8 = hitdef->air_guard_velocity_x_q8;
        v->gethit_vy_q8 = hitdef->air_guard_velocity_y_q8;
    } else {
        v->gethit_vx_q8 = hitdef->guard_velocity_x_q8;
        v->gethit_vy_q8 = 0;
    }

    a->move_contact = 1u;
    a->move_contact_time = fight->ko_split_clocks ? 1u : 0u;
    ikf_credit_hit_power(fight, a, v, hitdef, 1);
    ikf_hit_snap(fight, a, cns_for_fighter(fight, a), v, hitdef, 1);
    a->target_index = (int8_t)victim;
    a->target_id = hitdef->id;
    a->hitdef_target = (int8_t)victim;

    int32_t state = 150;
    if (type == IK_CNS_STATE_CROUCH) state = 152;
    else if (type == IK_CNS_STATE_AIR) state = 154;

    const ik_cns_asset_t* victim_cns =
        cns_for_owner(fight, v->owner_player);
    if (ik_cns_find_state(victim_cns, state)) {
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, state);
    } else {
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v,
                    type == IK_CNS_STATE_CROUCH ? 131 :
                    type == IK_CNS_STATE_AIR ? 132 : 130);
    }

    ikf_queue_hit_effect(
        fight, a, v, hitdef, hitdef->guard_spark_no, 0);
    ikf_queue_hitdef_sound(fight, a, 0, hitdef, 1);
    fight->events |= IK_EVENT_GUARD;
    if (guard_ko) {
        fight->winner = (uint8_t)((victim ^ 1) + 1);
        fight->events |= IK_EVENT_KO;
        fight->win_by_ko = 1u;
        if (!ik_cns_find_state(victim_cns, 5050)) {
            v->cur_move_type = IK_CNS_MOVE_HIT;
            v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
            v->ctrl = 0;
            ikf_enter_state_deferred(fight, v, IK_STATE_KO);
            fight->round_over = 1;
            fight->events |= IK_EVENT_ROUND_OVER;
            fight->ko_freeze = IK_KO_FREEZE_FRAMES;
        }
    }
}

void ikf_apply_throw(ik_fight_t* fight, int attacker,
                        const ik_fight_controls_t* attacker_controls,
                        const ik_cns_hitdef_t* hitdef) {
    if (!fight || !hitdef || attacker < 0 || attacker > 1) return;
    const int victim = attacker ^ 1;
    ik_fighter_t* a = &fight->fighters[attacker];
    ik_fighter_t* v = &fight->fighters[victim];

    ik_cns_hitdef_t evaluated_hitdef;
    if (hitdef->p1_state_no_expr_count ||
        hitdef->p2_state_no_expr_count ||
        hitdef->p1_facing_expr_count ||
        hitdef->p2_facing_expr_count ||
        hitdef->yaccel_expr_count) {
        evaluated_hitdef = *hitdef;
        const ik_cns_asset_t* cns = cns_for_fighter(fight, a);
        int32_t state_no = eval_fighter_integer_expr(
            fight, a, cns, hitdef->p1_state_no_expr_ofs,
            hitdef->p1_state_no_expr_count, hitdef->p1_state_no);
        evaluated_hitdef.p1_state_no = state_no;
        state_no = eval_fighter_integer_expr(
            fight, a, cns, hitdef->p2_state_no_expr_ofs,
            hitdef->p2_state_no_expr_count, hitdef->p2_state_no);
        evaluated_hitdef.p2_state_no = state_no;
        state_no = eval_fighter_integer_expr(
            fight, a, cns, hitdef->p1_facing_expr_ofs,
            hitdef->p1_facing_expr_count, hitdef->p1_facing);
        evaluated_hitdef.p1_facing = (int8_t)(
            state_no < INT8_MIN ? INT8_MIN :
            state_no > INT8_MAX ? INT8_MAX : state_no);
        state_no = eval_fighter_integer_expr(
            fight, a, cns, hitdef->p2_facing_expr_ofs,
            hitdef->p2_facing_expr_count, hitdef->p2_facing);
        evaluated_hitdef.p2_facing = (int8_t)(
            state_no < INT8_MIN ? INT8_MIN :
            state_no > INT8_MAX ? INT8_MAX : state_no);
        evaluated_hitdef.yaccel_q16 = eval_fighter_integer_expr(
            fight, a, cns, hitdef->yaccel_expr_ofs,
            hitdef->yaccel_expr_count, hitdef->yaccel_q16);
        evaluated_hitdef.yaccel_q8 = (int16_t)(
            evaluated_hitdef.yaccel_q16 / 256 < INT16_MIN ? INT16_MIN :
            evaluated_hitdef.yaccel_q16 / 256 > INT16_MAX ? INT16_MAX :
            evaluated_hitdef.yaccel_q16 / 256);
        hitdef = &evaluated_hitdef;
    }

    a->target_index = (int8_t)victim;
    a->target_id = hitdef->id;
    a->hitdef_target = (int8_t)victim;
    v->last_hit_owner = (int8_t)attacker;
    v->last_hit_id = hitdef->id;
    v->bound_to = (int8_t)attacker;
    v->bound_entity = ik_entity_invalid_handle();
    a->move_contact = 1u;
    a->move_contact_time = fight->ko_split_clocks ? 1u : 0u;
    ikf_credit_hit_power(fight, a, v, hitdef, 0);
    ikf_hit_snap(fight, a, cns_for_fighter(fight, a), v, hitdef, 0);
    ikf_record_hit(a, (uint8_t)victim);

    if (hitdef->p1_facing != 0) {
        const int8_t toward = v->x >= a->x ? 1 : -1;
        a->facing = hitdef->p1_facing > 0 ? toward : (int8_t)-toward;
    }
    if (hitdef->p2_facing != 0) {
        const int8_t toward = a->x >= v->x ? 1 : -1;
        v->facing = hitdef->p2_facing > 0 ? toward : (int8_t)-toward;
    }
    v->gethit_fall =
        (uint8_t)((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u);
    const ik_cns_asset_t* attack_cns = cns_for_fighter(fight, a);
    v->gethit_fall_x_q8 = eval_fighter_q8_expr(
        fight, a, attack_cns, hitdef->fall_x_velocity_expr_ofs,
        hitdef->fall_x_velocity_expr_count, hitdef->fall_x_velocity_q8);
    v->gethit_fall_y_q8 = eval_fighter_q8_expr(
        fight, a, attack_cns, hitdef->fall_y_velocity_expr_ofs,
        hitdef->fall_y_velocity_expr_count, hitdef->fall_y_velocity_q8);
    v->gethit_fall_x_set = hitdef->fall_x_velocity_set;
    v->gethit_fall_recover = eval_fighter_u8_expr(
        fight, a, attack_cns, hitdef->fall_recover_expr_ofs,
        hitdef->fall_recover_expr_count, hitdef->fall_recover);
    v->gethit_fall_recover_time = eval_fighter_u8_expr(
        fight, a, attack_cns, hitdef->fall_recover_time_expr_ofs,
        hitdef->fall_recover_time_expr_count, hitdef->fall_recover_time);

    if (hitdef->p2_state_no >= 0) {
        v->state_owner = a->state_owner;
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, hitdef->p2_state_no);
    }
    if (hitdef->p1_state_no >= 0) {
        ikf_enter_state_deferred(fight, a, hitdef->p1_state_no);
        int32_t priority = eval_fighter_integer_expr(
            fight, a, cns_for_fighter(fight, a),
            hitdef->p1_spr_priority_expr_ofs,
            hitdef->p1_spr_priority_expr_count,
            hitdef->p1_spr_priority);
        if (priority >= INT8_MIN && priority <= INT8_MAX && priority != -128) {
            a->spr_priority = (int8_t)priority;
        }
        /* KFM state 810 snapshots command="holdfwd" at Time=0. The throw
         * changes state during collision resolution, so preserve that entry
         * input in the generic state-axis scratch immediately. */
        if (attacker_controls) {
            if (attacker_controls->forward) a->state_axis = 1;
            else if (attacker_controls->back) a->state_axis = -1;
        }
    }

    ikf_queue_hit_effect(
        fight, a, v, hitdef, hitdef->spark_no, 1);
    ikf_queue_hitdef_sound(fight, a, 0, hitdef, 0);
    fight->events |= IK_EVENT_HIT;
    if (attacker == 0) ++fight->hits_p1;
    else ++fight->hits_p2;
}
