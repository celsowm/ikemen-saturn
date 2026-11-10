/* Resolve helper/projectile HitDef damage and get-hit state metadata. */
#include "ikemen_fight_internal.h"
#include "ikemen_fight_entity_hit_internal.h"
#include "ikemen_fight_hit_values.h"

void ikf_apply_damage_from_entity(
    ik_fight_t* fight,
    ik_entity_handle_t attacker_handle,
    int victim,
    const ik_cns_hitdef_t* hitdef,
    const ik_frame_table_t* p1_frames,
    const ik_frame_table_t* p2_frames
) {
    if (!fight || !fight->entities || !hitdef ||
        victim < 0 || victim > 1) {
        return;
    }
    ik_entity_t* attacker =
        ik_entity_get(fight->entities, attacker_handle);
    if (!attacker || attacker->owner_player >= 2u) return;

    ik_cns_hitdef_t evaluated_hitdef;
    if (hitdef->ground_velocity_x_expr_count ||
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
        hitdef->fall_envshake_freq_expr_count ||
        hitdef->p1_state_no_expr_count ||
        hitdef->p2_state_no_expr_count ||
        hitdef->p1_facing_expr_count ||
        hitdef->p2_facing_expr_count ||
        hitdef->yaccel_expr_count) {
        evaluated_hitdef = *hitdef;
        const ik_cns_asset_t* cns =
            cns_for_owner(fight, attacker->state_owner);
        int32_t value = 0;
        value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->p1_state_no_expr_ofs,
            hitdef->p1_state_no_expr_count, hitdef->p1_state_no);
        evaluated_hitdef.p1_state_no = value;
        value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->p2_state_no_expr_ofs,
            hitdef->p2_state_no_expr_count, hitdef->p2_state_no);
        evaluated_hitdef.p2_state_no = value;
        value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->p1_facing_expr_ofs,
            hitdef->p1_facing_expr_count, hitdef->p1_facing);
        evaluated_hitdef.p1_facing = (int8_t)(
            value < INT8_MIN ? INT8_MIN :
            value > INT8_MAX ? INT8_MAX : value);
        value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->p2_facing_expr_ofs,
            hitdef->p2_facing_expr_count, hitdef->p2_facing);
        evaluated_hitdef.p2_facing = (int8_t)(
            value < INT8_MIN ? INT8_MIN :
            value > INT8_MAX ? INT8_MAX : value);
        evaluated_hitdef.yaccel_q16 = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->yaccel_expr_ofs,
            hitdef->yaccel_expr_count, hitdef->yaccel_q16);
        evaluated_hitdef.yaccel_q8 = (int16_t)(
            evaluated_hitdef.yaccel_q16 / 256 < INT16_MIN ? INT16_MIN :
            evaluated_hitdef.yaccel_q16 / 256 > INT16_MAX ? INT16_MAX :
            evaluated_hitdef.yaccel_q16 / 256);
        if (hitdef->ground_velocity_x_expr_count &&
            ikf_eval_cns_entity_expr(
                fight, attacker, cns,
                hitdef->ground_velocity_x_expr_ofs,
                hitdef->ground_velocity_x_expr_count, &value)) {
            evaluated_hitdef.ground_velocity_x_q8 = (int16_t)(value / 256);
        }
        if (hitdef->ground_velocity_y_expr_count &&
            ikf_eval_cns_entity_expr(
                fight, attacker, cns,
                hitdef->ground_velocity_y_expr_ofs,
                hitdef->ground_velocity_y_expr_count, &value)) {
            evaluated_hitdef.ground_velocity_y_q8 = (int16_t)(value / 256);
        }
        if (hitdef->air_velocity_x_expr_count &&
            ikf_eval_cns_entity_expr(
                fight, attacker, cns,
                hitdef->air_velocity_x_expr_ofs,
                hitdef->air_velocity_x_expr_count, &value)) {
            evaluated_hitdef.air_velocity_x_q8 = (int16_t)(value / 256);
        }
        if (hitdef->air_velocity_y_expr_count &&
            ikf_eval_cns_entity_expr(
                fight, attacker, cns,
                hitdef->air_velocity_y_expr_ofs,
                hitdef->air_velocity_y_expr_count, &value)) {
            evaluated_hitdef.air_velocity_y_q8 = (int16_t)(value / 256);
        }
        const uint8_t fall_flag = eval_entity_u8_expr(
            fight, attacker, cns, hitdef->fall_expr_ofs,
            hitdef->fall_expr_count,
            (uint8_t)((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u));
        const uint8_t air_fall_flag = eval_entity_u8_expr(
            fight, attacker, cns, hitdef->air_fall_expr_ofs,
            hitdef->air_fall_expr_count,
            (uint8_t)((hitdef->flags & IK_CNS_HITDEF_AIR_FALL) != 0u));
        evaluated_hitdef.flags &= (uint8_t)~(
            IK_CNS_HITDEF_FALL | IK_CNS_HITDEF_AIR_FALL);
        if (fall_flag) evaluated_hitdef.flags |= IK_CNS_HITDEF_FALL;
        if (air_fall_flag) evaluated_hitdef.flags |= IK_CNS_HITDEF_AIR_FALL;
        evaluated_hitdef.ground_cornerpush_veloff_q8 =
            eval_entity_q8_expr(
                fight, attacker, cns,
                hitdef->ground_cornerpush_veloff_expr_ofs,
                hitdef->ground_cornerpush_veloff_expr_count,
                hitdef->ground_cornerpush_veloff_q8);
        int32_t dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->fall_damage_expr_ofs,
            hitdef->fall_damage_expr_count, hitdef->fall_damage);
        evaluated_hitdef.fall_damage = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->envshake_time_expr_ofs,
            hitdef->envshake_time_expr_count, hitdef->envshake_time);
        evaluated_hitdef.envshake_time = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->envshake_ampl_expr_ofs,
            hitdef->envshake_ampl_expr_count, hitdef->envshake_ampl);
        evaluated_hitdef.envshake_ampl = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->envshake_freq_expr_ofs,
            hitdef->envshake_freq_expr_count, hitdef->envshake_freq);
        evaluated_hitdef.envshake_freq = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->fall_envshake_time_expr_ofs,
            hitdef->fall_envshake_time_expr_count,
            hitdef->fall_envshake_time);
        evaluated_hitdef.fall_envshake_time = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->fall_envshake_ampl_expr_ofs,
            hitdef->fall_envshake_ampl_expr_count,
            hitdef->fall_envshake_ampl);
        evaluated_hitdef.fall_envshake_ampl = (int16_t)(
            dynamic_value < INT16_MIN ? INT16_MIN :
            dynamic_value > INT16_MAX ? INT16_MAX : dynamic_value);
        dynamic_value = eval_entity_integer_expr(
            fight, attacker, cns, hitdef->fall_envshake_freq_expr_ofs,
            hitdef->fall_envshake_freq_expr_count,
            hitdef->fall_envshake_freq);
        evaluated_hitdef.fall_envshake_freq = (uint16_t)(
            dynamic_value < 0 ? 0 :
            dynamic_value > UINT16_MAX ? UINT16_MAX : dynamic_value);
        evaluated_hitdef.ground_slide_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->ground_slide_time_expr_ofs,
            hitdef->ground_slide_time_expr_count,
            hitdef->ground_slide_time);
        evaluated_hitdef.ground_hit_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->ground_hit_time_expr_ofs,
            hitdef->ground_hit_time_expr_count, hitdef->ground_hit_time);
        evaluated_hitdef.air_hit_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->air_hit_time_expr_ofs,
            hitdef->air_hit_time_expr_count, hitdef->air_hit_time);
        evaluated_hitdef.guard_hit_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_hit_time_expr_ofs,
            hitdef->guard_hit_time_expr_count, hitdef->guard_hit_time);
        evaluated_hitdef.guard_slide_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_slide_time_expr_ofs,
            hitdef->guard_slide_time_expr_count,
            hitdef->guard_slide_time);
        evaluated_hitdef.guard_ctrl_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_ctrl_time_expr_ofs,
            hitdef->guard_ctrl_time_expr_count,
            hitdef->guard_ctrl_time);
        evaluated_hitdef.damage = eval_entity_damage_expr(
            fight, attacker, cns, hitdef->damage_expr_ofs,
            hitdef->damage_expr_count, hitdef->damage);
        evaluated_hitdef.guard_damage = eval_entity_damage_expr(
            fight, attacker, cns, hitdef->guard_damage_expr_ofs,
            hitdef->guard_damage_expr_count, hitdef->guard_damage);
        evaluated_hitdef.pause_p1 = eval_entity_time_expr(
            fight, attacker, cns, hitdef->pause_p1_expr_ofs,
            hitdef->pause_p1_expr_count, hitdef->pause_p1);
        evaluated_hitdef.pause_p2 = eval_entity_time_expr(
            fight, attacker, cns, hitdef->pause_p2_expr_ofs,
            hitdef->pause_p2_expr_count, hitdef->pause_p2);
        hitdef = &evaluated_hitdef;
    }

    ik_fighter_t* v = &fight->fighters[victim];
    (void)ik_entity_add_target(
        fight->entities, attacker_handle,
        fight->player_entities[victim], hitdef->id);
    v->last_hit_owner = (int8_t)attacker->owner_player;
    v->last_hit_id = hitdef->id;
    ikf_release_bound_target(fight, victim);
    ikf_release_entity_bound_fighter(fight, v);

    const uint8_t victim_type = ik_fight_state_type(fight, v);
    const int downed = victim_type == IK_CNS_STATE_LIEDOWN;
    const int airborne = !v->on_ground || victim_type == IK_CNS_STATE_AIR;
    const int16_t velocity_x = downed
        ? hitdef->down_velocity_x_q8
        : airborne
            ? hitdef->air_velocity_x_q8
            : hitdef->ground_velocity_x_q8;
    const int16_t velocity_y = downed
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
    const int attack_juggle =
        ikf_entity_juggle_cost(fight, attacker, hitdef);
    const int downed_launch = downed && velocity_y != 0;
    const int launch = airborne || downed_launch ||
        (hitdef->flags & IK_CNS_HITDEF_FALL) != 0u ||
        velocity_y != 0;

    int damage = hitdef->damage;
    if (hitdef->has_alt_damage &&
        attacker->prev_state_no == hitdef->alt_damage_prev_state) {
        damage = hitdef->alt_damage;
    }
    const int32_t attack_mul_q16 = attacker->type == IK_ENTITY_PROJECTILE
        ? attacker->projectile_parent_attack_mul_q16
        : attacker->attack_mul_q16;
    const ik_fighter_t* attack_owner =
        &fight->fighters[attacker->owner_player];
    damage = ikf_scale_character_damage(
        damage, attack_mul_q16,
        constants_for_fighter(fight, attack_owner),
        constants_for_fighter(fight, v),
        ikf_active_custom_defense_q16(v));

    int pending_damage = v->pending_damage + damage;
    if (((v->assert_controller_flags & IK_CNS_ASSERT_NO_KO) != 0u ||
         (fight->global_assert_controller_flags &
          IK_CNS_GLOBAL_ASSERT_NO_KO) != 0u) &&
        v->hp > 0 && pending_damage >= v->hp) {
        pending_damage = v->hp - 1;
    }
    v->pending_damage = (int16_t)pending_damage;
    const int hp_after = v->hp - v->pending_damage;
    /* Upstream's HitOver is hittime < 0, so it takes hit_time + 1 ticks. */
    ikf_record_received_hit(v);
    v->hitstun = (uint16_t)(hit_time < 0 ? 0 : hit_time + 1);
    v->hit_shake_time = hitdef->pause_p2;
    v->hit_slide_time = downed && velocity_y == 0
        ? hitdef->down_hit_time
        : hitdef->ground_slide_time;
    v->hit_ctrl_time = (uint16_t)(hit_time < 0 ? 0 : hit_time);
    v->gethit_vx_q8 = velocity_x;
    v->gethit_vy_q8 = velocity_y;
    v->gethit_yaccel_q8 = hitdef->yaccel_q8;
    v->gethit_yaccel_q16 = hitdef->yaccel_q16;
    v->gethit_ground_type = hitdef->ground_type;
    v->gethit_air_type = hitdef->air_type;
    v->gethit_fall = (uint8_t)(
        ((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u) ||
        (airborne &&
         (hitdef->flags & IK_CNS_HITDEF_AIR_FALL) != 0u) ||
        downed_launch);
    v->gethit_anim_type = ikf_gethit_anim_type(
        hitdef, v->gethit_fall, airborne, velocity_y);
    v->gethit_fall_x_q8 = hitdef->fall_x_velocity_q8;
    v->gethit_fall_y_q8 =
        (downed_launch && !hitdef->down_bounce)
            ? 0 : hitdef->fall_y_velocity_q8;
    v->gethit_fall_x_set =
        (uint8_t)(hitdef->fall_x_velocity_set &&
                  (!downed_launch || hitdef->down_bounce));
    const ik_cns_asset_t* attack_cns =
        cns_for_owner(fight, attacker->state_owner);
    v->gethit_fall_recover = eval_entity_u8_expr(
        fight, attacker, attack_cns, hitdef->fall_recover_expr_ofs,
        hitdef->fall_recover_expr_count, hitdef->fall_recover);
    v->gethit_fall_recover_time = eval_entity_u8_expr(
        fight, attacker, attack_cns, hitdef->fall_recover_time_expr_ofs,
        hitdef->fall_recover_time_expr_count, hitdef->fall_recover_time);
    v->gethit_fall_damage = hitdef->fall_damage;
    v->gethit_fall_envshake_time = hitdef->fall_envshake_time;
    v->gethit_fall_envshake_ampl = hitdef->fall_envshake_ampl;
    v->gethit_fall_envshake_freq = hitdef->fall_envshake_freq;
    v->fall_time = 0u;

    if (was_juggle_target && attacker->owner_player < 2u &&
        (fight->fighters[attacker->owner_player].assert_controller_flags &
         IK_CNS_ASSERT_NO_JUGGLE_CHECK) == 0u) {
        v->juggle_points = (int16_t)(
            v->juggle_points > attack_juggle
                ? v->juggle_points - attack_juggle : 0);
    } else if ((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u) {
        const ik_cns_constants_t* constants =
            constants_for_fighter(fight, v);
        const int initial =
            (constants && constants->air_juggle > 0)
                ? constants->air_juggle : 15;
        v->juggle_points = (int16_t)(
            initial > attack_juggle
                ? initial - attack_juggle : 0);
    }

    attacker->hit_pause = hitdef->pause_p1;
    if (hitdef->envshake_time > 0u) {
        fight->env_shake_time = hitdef->envshake_time;
        fight->env_shake_ampl = hitdef->envshake_ampl;
        fight->env_shake_freq = hitdef->envshake_freq;
        fight->env_shake_phase = 0u;
    }
    attacker->move_contact = 1u;
    ikf_credit_hit_power(
        fight, &fight->fighters[attacker->owner_player], v, hitdef, 0);
    record_entity_hit(fight, attacker);
    if (launch) v->on_ground = 0;

    if (!airborne && !downed &&
        hitdef->ground_cornerpush_veloff_q8 != 0) {
        int left = 0, top = 0, right = 0, bottom = 0;
        ik_body_box(v, &left, &top, &right, &bottom);
        if (left <= (v->xmin_q8 / IK_CNS_Q8_ONE) ||
            right >= (v->xmax_q8 / IK_CNS_Q8_ONE)) {
            attacker->vx_q8 =
                (int32_t)attacker->facing *
                hitdef->ground_cornerpush_veloff_q8;
        }
    }

    int16_t target = IK_STATE_HIT;
    int custom_p2_state = 0;
    const ik_cns_asset_t* attacker_cns =
        cns_for_owner(fight, attacker->state_owner);
    const ik_cns_asset_t* victim_cns =
        cns_for_owner(fight, v->owner_player);
    const uint8_t p2_get_p1_state = eval_entity_u8_expr(
        fight, attacker, attacker_cns,
        hitdef->p2_get_p1_state_expr_ofs,
        hitdef->p2_get_p1_state_expr_count,
        hitdef->p2_get_p1_state);
    const ik_cns_asset_t* p2_state_cns = p2_get_p1_state
        ? attacker_cns : victim_cns;
    if (hitdef->p2_state_no >= 0 &&
        ik_cns_find_state(p2_state_cns, hitdef->p2_state_no)) {
        target = hitdef->p2_state_no;
        custom_p2_state = 1;
    } else if (victim_type == IK_CNS_STATE_LIEDOWN &&
               ik_cns_find_state(victim_cns, 5080)) {
        target = 5080;
    } else if (!airborne &&
               hitdef->ground_type == IK_CNS_GROUND_TRIP &&
               ik_cns_find_state(victim_cns, 5070)) {
        target = 5070;
    } else if (airborne &&
               ik_cns_find_state(victim_cns, 5020)) {
        target = 5020;
    } else if (victim_type == IK_CNS_STATE_CROUCH &&
               (hitdef->flags & IK_CNS_HITDEF_FORCE_STAND) == 0u &&
               ik_cns_find_state(victim_cns, 5010)) {
        target = 5010;
    } else if (ik_cns_find_state(victim_cns, 5000)) {
        target = 5000;
    }

    if (hitdef->p2_facing != 0) {
        const int attacker_x = ik_cns_q8_to_int(attacker->x_q8);
        const int8_t toward = attacker_x >= v->x ? 1 : -1;
        v->facing =
            hitdef->p2_facing > 0 ? toward : (int8_t)-toward;
    }

    /* A compiled get-hit state keeps the current velocity until its StateDef
     * (velset) applies on the victim's next tick. */
    if (target == IK_STATE_HIT) {
        v->vx_q8 = (int32_t)v->facing * velocity_x;
        v->vy_q8 = velocity_y;
    }

    ikf_queue_entity_hit_effect(
        fight, attacker, v, hitdef, hitdef->spark_no, 1);
    ikf_queue_hitdef_sound(fight, 0, attacker, hitdef, 0);
    if (hp_after <= 0) {
        v->pending_damage = v->hp;
        fight->winner = (uint8_t)(attacker->owner_player + 1u);
        fight->events |= (uint16_t)(IK_EVENT_HIT | IK_EVENT_KO);
        fight->win_by_ko = 1u;
    } else {
        fight->events |= IK_EVENT_HIT;
    }

    if (target == IK_STATE_HIT && hp_after <= 0) {
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)attacker->owner_player;
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, IK_STATE_KO);
        fight->round_over = 1;
        fight->events |= IK_EVENT_ROUND_OVER;
        fight->ko_freeze = IK_KO_FREEZE_FRAMES;
    } else {
        if (custom_p2_state && p2_get_p1_state) {
            v->state_owner = attacker->state_owner;
        }
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)attacker->owner_player;
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, target);
    }

    if (hitdef->p1_state_no >= 0 &&
        ik_cns_find_state(
            cns_for_owner(fight, attacker->state_owner),
            hitdef->p1_state_no)) {
        enter_entity_contact_state(
            fight, attacker_handle, hitdef->p1_state_no,
            p1_frames, p2_frames);
    }

    if (attacker->owner_player == 0u) ++fight->hits_p1;
    else ++fight->hits_p2;
}

