/* Applying a resolved hit from a root fighter: guard, throw, damage. */
#include "ikemen_fight_internal.h"

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

static uint8_t eval_fighter_time_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    uint8_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_expr(
            fight, fighter, cns, offset, count, &value)) {
        return fallback;
    }
    if (value < 0) return 0u;
    if (value > UINT8_MAX) return UINT8_MAX;
    return (uint8_t)value;
}

static int32_t eval_fighter_integer_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int32_t fallback
) {
    int32_t value = 0;
    return count && ikf_eval_cns_expr(
        fight, fighter, cns, offset, count, &value) ? value : fallback;
}

static int16_t eval_fighter_damage_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int16_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_expr(
            fight, fighter, cns, offset, count, &value)) {
        return fallback;
    }
    if (value < INT16_MIN) return INT16_MIN;
    if (value > INT16_MAX) return INT16_MAX;
    return (int16_t)value;
}

static uint8_t eval_fighter_u8_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    uint8_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_expr(
            fight, fighter, cns, offset, count, &value)) return fallback;
    if (value < 0) return 0u;
    if (value > UINT8_MAX) return UINT8_MAX;
    return (uint8_t)value;
}

static int16_t eval_fighter_q8_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int16_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_expr(
            fight, fighter, cns, offset, count, &value)) return fallback;
    value /= 256;
    if (value < INT16_MIN) return INT16_MIN;
    if (value > INT16_MAX) return INT16_MAX;
    return (int16_t)value;
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
    ik_fighter_t* v = &fight->fighters[victim];
    ik_fighter_t* a = &fight->fighters[victim ^ 1];
    ik_cns_hitdef_t evaluated_hitdef;
    if (hitdef && (hitdef->guard_hit_time_expr_count ||
                   hitdef->guard_slide_time_expr_count ||
                   hitdef->guard_ctrl_time_expr_count ||
                   hitdef->guard_damage_expr_count ||
                   hitdef->pause_p1_expr_count ||
                   hitdef->pause_p2_expr_count ||
                   hitdef->fall_x_velocity_expr_count ||
                   hitdef->fall_y_velocity_expr_count ||
                   hitdef->guard_velocity_x_expr_count)) {
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
            if (hitdef->guard_kill) {
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
    ikf_hit_snap(a, v, hitdef, 1);
    a->target_index = (int8_t)victim;
    a->target_id = hitdef->id;
    a->hitdef_target = (int8_t)victim;

    int16_t state = 150;
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
    ikf_hit_snap(a, v, hitdef, 0);
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
        if (hitdef->p1_spr_priority != -128) {
            a->spr_priority = hitdef->p1_spr_priority;
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

static void apply_ko_velocity(
    const ik_cns_constants_t* constants,
    uint8_t state_type,
    int32_t* vx_q8,
    int32_t* vy_q8
) {
    if (!vx_q8 || !vy_q8 || state_type == IK_CNS_STATE_LIEDOWN) return;

    /* Hand-built host fixtures predate these fields. Generated character
     * assets set ko_velocity_defined and therefore preserve authored zeroes. */
    const int defined = constants && constants->ko_velocity_defined;
    const int16_t air_add_x = defined
        ? constants->air_gethit_ko_add_x_q8 : -640;   /* -2.5 */
    const int16_t air_add_y = defined
        ? constants->air_gethit_ko_add_y_q8 : -512;   /* -2.0 */
    const int16_t air_ymin = defined
        ? constants->air_gethit_ko_ymin_q8 : -768;    /* -3.0 */
    const int32_t ground_xmul = defined
        ? constants->ground_gethit_ko_xmul_q16 : 43254; /* 0.66 */
    const int16_t ground_add_x = defined
        ? constants->ground_gethit_ko_add_x_q8 : -640;
    const int16_t ground_add_y = defined
        ? constants->ground_gethit_ko_add_y_q8 : -512;
    const int16_t ground_ymin = defined
        ? constants->ground_gethit_ko_ymin_q8 : -1536; /* -6.0 */

    if (state_type == IK_CNS_STATE_AIR) {
        if (*vx_q8 != 0) {
            *vx_q8 += *vx_q8 > 0 ? -air_add_x : air_add_x;
        }
        if (*vy_q8 <= 0) {
            *vy_q8 += air_add_y;
            if (*vy_q8 > air_ymin) *vy_q8 = air_ymin;
        }
        return;
    }

    if (*vy_q8 == 0) {
        *vx_q8 = (int32_t)(((int64_t)*vx_q8 * ground_xmul) / 65536);
    }
    if (*vx_q8 != 0) {
        *vx_q8 += *vx_q8 > 0 ? -ground_add_x : ground_add_x;
    }
    if (*vy_q8 <= 0) {
        *vy_q8 += ground_add_y;
        if (*vy_q8 > ground_ymin) *vy_q8 = ground_ymin;
    }
}

void ikf_apply_damage(ik_fight_t* fight, int victim,
                         const ik_cns_hitdef_t* hitdef) {
    ik_cns_hitdef_t evaluated_hitdef;
    ik_fighter_t* v = &fight->fighters[victim];
    const int attacker = victim ^ 1;
    if (hitdef && (hitdef->ground_velocity_x_expr_count ||
                   hitdef->ground_velocity_y_expr_count ||
                   hitdef->air_velocity_x_expr_count ||
                   hitdef->air_velocity_y_expr_count ||
                   hitdef->ground_slide_time_expr_count ||
                   hitdef->ground_hit_time_expr_count ||
                   hitdef->air_hit_time_expr_count ||
                   hitdef->guard_hit_time_expr_count ||
                   hitdef->guard_slide_time_expr_count ||
                   hitdef->guard_ctrl_time_expr_count ||
                   hitdef->damage_expr_count ||
                   hitdef->guard_damage_expr_count ||
                   hitdef->pause_p1_expr_count ||
                   hitdef->pause_p2_expr_count ||
                   hitdef->fall_expr_count ||
                   hitdef->air_fall_expr_count ||
                   hitdef->ground_cornerpush_veloff_expr_count ||
                   hitdef->fall_damage_expr_count ||
                   hitdef->envshake_time_expr_count ||
                   hitdef->envshake_ampl_expr_count ||
                   hitdef->envshake_freq_expr_count ||
                   hitdef->fall_envshake_time_expr_count ||
                   hitdef->fall_envshake_ampl_expr_count ||
                   hitdef->fall_envshake_freq_expr_count)) {
        evaluated_hitdef = *hitdef;
        const ik_cns_asset_t* cns =
            cns_for_fighter(fight, &fight->fighters[attacker]);
        int32_t value = 0;
        if (hitdef->ground_velocity_x_expr_count &&
            ikf_eval_cns_expr(
                fight, &fight->fighters[attacker], cns,
                hitdef->ground_velocity_x_expr_ofs,
                hitdef->ground_velocity_x_expr_count, &value)) {
            evaluated_hitdef.ground_velocity_x_q8 = (int16_t)(value / 256);
        }
        if (hitdef->ground_velocity_y_expr_count &&
            ikf_eval_cns_expr(
                fight, &fight->fighters[attacker], cns,
                hitdef->ground_velocity_y_expr_ofs,
                hitdef->ground_velocity_y_expr_count, &value)) {
            evaluated_hitdef.ground_velocity_y_q8 = (int16_t)(value / 256);
        }
        if (hitdef->air_velocity_x_expr_count &&
            ikf_eval_cns_expr(
                fight, &fight->fighters[attacker], cns,
                hitdef->air_velocity_x_expr_ofs,
                hitdef->air_velocity_x_expr_count, &value)) {
            evaluated_hitdef.air_velocity_x_q8 = (int16_t)(value / 256);
        }
        if (hitdef->air_velocity_y_expr_count &&
            ikf_eval_cns_expr(
                fight, &fight->fighters[attacker], cns,
                hitdef->air_velocity_y_expr_ofs,
                hitdef->air_velocity_y_expr_count, &value)) {
            evaluated_hitdef.air_velocity_y_q8 = (int16_t)(value / 256);
        }
        evaluated_hitdef.ground_slide_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->ground_slide_time_expr_ofs,
            hitdef->ground_slide_time_expr_count,
            hitdef->ground_slide_time);
        evaluated_hitdef.ground_hit_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->ground_hit_time_expr_ofs,
            hitdef->ground_hit_time_expr_count,
            hitdef->ground_hit_time);
        evaluated_hitdef.air_hit_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->air_hit_time_expr_ofs,
            hitdef->air_hit_time_expr_count, hitdef->air_hit_time);
        evaluated_hitdef.guard_hit_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->guard_hit_time_expr_ofs,
            hitdef->guard_hit_time_expr_count, hitdef->guard_hit_time);
        evaluated_hitdef.guard_slide_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->guard_slide_time_expr_ofs,
            hitdef->guard_slide_time_expr_count,
            hitdef->guard_slide_time);
        evaluated_hitdef.guard_ctrl_time = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->guard_ctrl_time_expr_ofs,
            hitdef->guard_ctrl_time_expr_count,
            hitdef->guard_ctrl_time);
        evaluated_hitdef.damage = eval_fighter_damage_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->damage_expr_ofs, hitdef->damage_expr_count,
            hitdef->damage);
        evaluated_hitdef.guard_damage = eval_fighter_damage_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->guard_damage_expr_ofs, hitdef->guard_damage_expr_count,
            hitdef->guard_damage);
        evaluated_hitdef.pause_p1 = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->pause_p1_expr_ofs, hitdef->pause_p1_expr_count,
            hitdef->pause_p1);
        evaluated_hitdef.pause_p2 = eval_fighter_time_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->pause_p2_expr_ofs, hitdef->pause_p2_expr_count,
            hitdef->pause_p2);
        evaluated_hitdef.fall_x_velocity_q8 = eval_fighter_q8_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_x_velocity_expr_ofs,
            hitdef->fall_x_velocity_expr_count,
            hitdef->fall_x_velocity_q8);
        evaluated_hitdef.fall_y_velocity_q8 = eval_fighter_q8_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_y_velocity_expr_ofs,
            hitdef->fall_y_velocity_expr_count,
            hitdef->fall_y_velocity_q8);
        const uint8_t fall_flag = eval_fighter_u8_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_expr_ofs, hitdef->fall_expr_count,
            (uint8_t)((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u));
        const uint8_t air_fall_flag = eval_fighter_u8_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->air_fall_expr_ofs, hitdef->air_fall_expr_count,
            (uint8_t)((hitdef->flags & IK_CNS_HITDEF_AIR_FALL) != 0u));
        evaluated_hitdef.flags &= (uint8_t)~(
            IK_CNS_HITDEF_FALL | IK_CNS_HITDEF_AIR_FALL);
        if (fall_flag) evaluated_hitdef.flags |= IK_CNS_HITDEF_FALL;
        if (air_fall_flag) evaluated_hitdef.flags |= IK_CNS_HITDEF_AIR_FALL;
        evaluated_hitdef.ground_cornerpush_veloff_q8 =
            eval_fighter_q8_expr(
                fight, &fight->fighters[attacker], cns,
                hitdef->ground_cornerpush_veloff_expr_ofs,
                hitdef->ground_cornerpush_veloff_expr_count,
                hitdef->ground_cornerpush_veloff_q8);
        int32_t dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_damage_expr_ofs, hitdef->fall_damage_expr_count,
            hitdef->fall_damage);
        evaluated_hitdef.fall_damage = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->envshake_time_expr_ofs, hitdef->envshake_time_expr_count,
            hitdef->envshake_time);
        evaluated_hitdef.envshake_time = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->envshake_ampl_expr_ofs, hitdef->envshake_ampl_expr_count,
            hitdef->envshake_ampl);
        evaluated_hitdef.envshake_ampl = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->envshake_freq_expr_ofs, hitdef->envshake_freq_expr_count,
            hitdef->envshake_freq);
        evaluated_hitdef.envshake_freq = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_envshake_time_expr_ofs,
            hitdef->fall_envshake_time_expr_count,
            hitdef->fall_envshake_time);
        evaluated_hitdef.fall_envshake_time = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_envshake_ampl_expr_ofs,
            hitdef->fall_envshake_ampl_expr_count,
            hitdef->fall_envshake_ampl);
        evaluated_hitdef.fall_envshake_ampl = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_fighter_integer_expr(
            fight, &fight->fighters[attacker], cns,
            hitdef->fall_envshake_freq_expr_ofs,
            hitdef->fall_envshake_freq_expr_count,
            hitdef->fall_envshake_freq);
        evaluated_hitdef.fall_envshake_freq = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        hitdef = &evaluated_hitdef;
    }
    fight->fighters[attacker].target_index = (int8_t)victim;
    fight->fighters[attacker].target_id = hitdef ? hitdef->id : 0;
    fight->fighters[attacker].hitdef_target = (int8_t)victim;
    v->last_hit_owner = (int8_t)attacker;
    v->last_hit_id = hitdef ? hitdef->id : 0;
    /* Losing a throw owner releases its bound target. State 820's compiled
     * !isbound SelfState then returns the target to its own fall graph. */
    ikf_release_bound_target(fight, victim);
    ikf_release_entity_bound_fighter(fight, v);
    ik_fighter_t* a = &fight->fighters[victim ^ 1];

    const int victim_was_dead = v->hp <= 0;
    const uint8_t victim_type = ik_fight_state_type(fight, v);
    const int downed = victim_type == IK_CNS_STATE_LIEDOWN;
    const int airborne = !v->on_ground || victim_type == IK_CNS_STATE_AIR;
    int32_t velocity_x = downed
        ? hitdef->down_velocity_x_q8
        : airborne
            ? hitdef->air_velocity_x_q8
            : hitdef->ground_velocity_x_q8;
    int32_t velocity_y = downed
        ? hitdef->down_velocity_y_q8
        : airborne
            ? hitdef->air_velocity_y_q8
            : hitdef->ground_velocity_y_q8;
    const int16_t hit_time = downed
        ? (velocity_y == 0
            ? (int16_t)hitdef->down_hit_time
            : (int16_t)hitdef->air_hit_time)
        : airborne
            ? (int16_t)hitdef->air_hit_time
            : (int16_t)hitdef->ground_hit_time;
    const int was_juggle_target = ikf_is_juggle_target(fight, v);
    const int attack_juggle = ikf_juggle_cost(fight, a, hitdef);
    const int downed_launch = downed && velocity_y != 0;

    int damage = hitdef->damage;
    if (hitdef->has_alt_damage &&
        a->prev_state == hitdef->alt_damage_prev_state) {
        damage = hitdef->alt_damage;
    }
    v->pending_damage = (int16_t)(v->pending_damage + damage);
    const int hp_after = v->hp - v->pending_damage;
    const int ko = hp_after <= 0;
    if (ko) {
        /* Ikemen modifies the stored get-hit velocity immediately on a
         * lethal contact. The branch is based on the victim's pre-hit
         * StateType (A vs S/C; L is intentionally untouched). */
        apply_ko_velocity(
            constants_for_fighter(fight, v), victim_type,
            &velocity_x, &velocity_y);
    }
    const int launch = ko || airborne || downed_launch ||
        (hitdef->flags & IK_CNS_HITDEF_FALL) != 0u ||
        velocity_y != 0;
    /* Upstream's HitOver is hittime < 0, so it takes hit_time + 1 ticks. */
    ikf_record_received_hit(v);
    v->hitstun = (uint16_t)(hit_time < 0 ? 0 : hit_time + 1);
    v->hit_shake_time = hitdef->pause_p2;
    v->hit_slide_time = downed && velocity_y == 0
        ? hitdef->down_hit_time
        : hitdef->ground_slide_time;
    v->hit_ctrl_time = (uint16_t)(hit_time < 0 ? 0 : hit_time);
    v->gethit_vx_q8 = (int16_t)velocity_x;
    v->gethit_vy_q8 = (int16_t)velocity_y;
    v->gethit_yaccel_q8 = hitdef->yaccel_q8;
    v->gethit_yaccel_q16 = hitdef->yaccel_q16;
    v->gethit_ground_type = hitdef->ground_type;
    /* A liedown victim launched by down.velocity always enters the fall
     * graph so it returns to a downed state on landing. down.bounce only
     * controls whether state 5100 receives a non-zero fall Y velocity and
     * therefore proceeds through the single 5101 ground bounce. */
    v->gethit_fall = (uint8_t)(
        ko ||
        ((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u) ||
        (airborne &&
         (hitdef->flags & IK_CNS_HITDEF_AIR_FALL) != 0u) ||
        downed_launch);
    v->gethit_anim_type = ikf_gethit_anim_type(
        hitdef, v->gethit_fall, airborne, velocity_y);
    v->gethit_fall_x_q8 = hitdef->fall_x_velocity_q8;
    v->gethit_fall_y_q8 =
        (downed_launch && !hitdef->down_bounce)
            ? 0
            : hitdef->fall_y_velocity_q8;
    v->gethit_fall_x_set =
        (uint8_t)(hitdef->fall_x_velocity_set &&
                  (!downed_launch || hitdef->down_bounce));
    const ik_cns_asset_t* attack_cns = cns_for_fighter(fight, a);
    v->gethit_fall_recover = eval_fighter_u8_expr(
        fight, a, attack_cns, hitdef->fall_recover_expr_ofs,
        hitdef->fall_recover_expr_count, hitdef->fall_recover);
    v->gethit_fall_recover_time = eval_fighter_u8_expr(
        fight, a, attack_cns, hitdef->fall_recover_time_expr_ofs,
        hitdef->fall_recover_time_expr_count, hitdef->fall_recover_time);
    v->gethit_fall_damage = hitdef->fall_damage;
    v->gethit_fall_envshake_time = hitdef->fall_envshake_time;
    v->gethit_fall_envshake_ampl = hitdef->fall_envshake_ampl;
    v->gethit_fall_envshake_freq = hitdef->fall_envshake_freq;
    v->fall_time = 0u;

    /* Once life is already zero, Ikemen can still accept authored follow-up
     * hits during the KO sequence, but they do not consume a second slice of
     * the air-juggle budget. The deciding hit above already established it. */
    if (!victim_was_dead) {
        if (was_juggle_target) {
            v->juggle_points = (int16_t)(
                v->juggle_points > attack_juggle
                    ? v->juggle_points - attack_juggle
                    : 0);
        } else if ((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u || ko) {
            /* A KO forces fallflag upstream even when the connecting ground
             * HitDef is not itself a fall hit. That also starts the victim's
             * air-juggle budget on the deciding contact. */
            const ik_cns_constants_t* c = constants_for_fighter(fight, v);
            const int initial = (c && c->air_juggle > 0) ? c->air_juggle : 15;
            v->juggle_points =
                (int16_t)(initial > attack_juggle ? initial - attack_juggle : 0);
        }
    }

    a->hit_pause = hitdef->pause_p1;

    if (hitdef->envshake_time > 0u) {
        fight->env_shake_time = hitdef->envshake_time;
        fight->env_shake_ampl = hitdef->envshake_ampl;
        fight->env_shake_freq = hitdef->envshake_freq;
        fight->env_shake_phase = 0u;
    }

    if (launch) v->on_ground = 0;

    a->move_contact = 1u;
    a->move_contact_time = fight->ko_split_clocks ? 1u : 0u;
    /* Ikemen still records the authored KO follow-up contact, but a target
     * whose life was already zero does not award another get/give-power
     * packet. The deciding hit already credited both sides. */
    if (!victim_was_dead) {
        ikf_credit_hit_power(fight, a, v, hitdef, 0);
    }
    ikf_hit_snap(a, v, hitdef, 0);
    ikf_record_hit(a, (uint8_t)victim);

    if (!airborne && !downed &&
        hitdef->ground_cornerpush_veloff_q8 != 0) {
        int left=0, top=0, right=0, bottom=0;
        ik_body_box(v, &left, &top, &right, &bottom);
        if (left <= (v->xmin_q8 / IK_CNS_Q8_ONE) ||
            right >= (v->xmax_q8 / IK_CNS_Q8_ONE)) {
            a->vx_q8 =
                (int32_t)a->facing * hitdef->ground_cornerpush_veloff_q8;
        }
    }

    {
        int16_t target = IK_STATE_HIT;
        int custom_p2_state = 0;
        const ik_cns_asset_t* attacker_cns = cns_for_fighter(fight, a);
        const ik_cns_asset_t* victim_cns =
            cns_for_owner(fight, v->owner_player);
        if (hitdef->p2_state_no >= 0 &&
            ik_cns_find_state(attacker_cns, hitdef->p2_state_no)) {
            target = hitdef->p2_state_no;
            custom_p2_state = 1;
        } else if (victim_type == IK_CNS_STATE_LIEDOWN &&
            ik_cns_find_state(victim_cns, 5080)) {
            target = 5080;
        } else if (!airborne && hitdef->ground_type == IK_CNS_GROUND_TRIP &&
                   ik_cns_find_state(victim_cns, 5070)) {
            target = 5070;
        } else if (airborne && ik_cns_find_state(victim_cns, 5020)) {
            target = 5020;
        } else if (victim_type == IK_CNS_STATE_CROUCH &&
                   (hitdef->flags & IK_CNS_HITDEF_FORCE_STAND) == 0u &&
                   ik_cns_find_state(victim_cns, 5010)) {
            target = 5010;
        } else if (ik_cns_find_state(victim_cns, 5000)) {
            target = 5000;
        }

        if (hitdef->p2_facing != 0) {
            const int8_t toward = a->x >= v->x ? 1 : -1;
            v->facing =
                hitdef->p2_facing > 0 ? toward : (int8_t)-toward;
        }

        /* A compiled get-hit state keeps the current velocity until its
         * StateDef (velset) applies on the victim's next tick. */
        if (target == IK_STATE_HIT) {
            v->vx_q8 = (int32_t)v->facing * velocity_x;
            v->vy_q8 = velocity_y;
        }

        ikf_queue_hit_effect(
            fight, a, v, hitdef, hitdef->spark_no, 1);
        ikf_queue_hitdef_sound(fight, a, 0, hitdef, 0);
        if (hp_after <= 0) {
            v->pending_damage = v->hp;
            fight->winner = (uint8_t)((victim ^ 1) + 1);
            fight->events |= (uint16_t)(IK_EVENT_HIT | IK_EVENT_KO);
        } else {
            fight->events |= IK_EVENT_HIT;
        }

        if (target == IK_STATE_HIT && hp_after <= 0) {
            v->cur_move_type = IK_CNS_MOVE_HIT;
            v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
            v->ctrl = 0;
            ikf_enter_state_deferred(fight, v, IK_STATE_KO);
            fight->round_over = 1;
            fight->events |= IK_EVENT_ROUND_OVER;
            fight->ko_freeze = IK_KO_FREEZE_FRAMES;
        } else {
            if (custom_p2_state) v->state_owner = a->state_owner;
            v->cur_move_type = IK_CNS_MOVE_HIT;
            v->juggle_owner = (int8_t)ikf_fighter_player_index(fight, a);
            v->ctrl = 0;
            ikf_enter_state_deferred(fight, v, target);
        }
    }

    if (hitdef->p1_state_no >= 0 &&
        ik_cns_find_state(
            cns_for_fighter(fight, a), hitdef->p1_state_no)) {
        ikf_enter_state_deferred(fight, a, hitdef->p1_state_no);
    }

    if ((victim ^ 1) == 0) fight->hits_p1++;
    else fight->hits_p2++;
}
