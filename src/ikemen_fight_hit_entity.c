/* Resolve guard and throw contacts from helper/projectile owners. */
#include "ikemen_fight_internal.h"
#include "ikemen_fight_entity_hit_internal.h"

void ikf_apply_guard_from_entity(
    ik_fight_t* fight,
    ik_entity_handle_t attacker_handle,
    int victim,
    const ik_fight_controls_t* controls,
    const ik_cns_hitdef_t* hitdef
) {
    if (!fight || !fight->entities || !hitdef ||
        victim < 0 || victim > 1) {
        return;
    }
    ik_entity_t* attacker =
        ik_entity_get(fight->entities, attacker_handle);
    if (!attacker || attacker->owner_player >= 2u) return;

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
        const ik_cns_asset_t* cns =
            cns_for_owner(fight, attacker->state_owner);
        evaluated_hitdef.guard_hit_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_hit_time_expr_ofs,
            hitdef->guard_hit_time_expr_count, hitdef->guard_hit_time);
        evaluated_hitdef.guard_slide_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_slide_time_expr_ofs,
            hitdef->guard_slide_time_expr_count,
            hitdef->guard_slide_time);
        evaluated_hitdef.guard_ctrl_time = eval_entity_time_expr(
            fight, attacker, cns, hitdef->guard_ctrl_time_expr_ofs,
            hitdef->guard_ctrl_time_expr_count, hitdef->guard_ctrl_time);
        evaluated_hitdef.guard_damage = eval_entity_damage_expr(
            fight, attacker, cns, hitdef->guard_damage_expr_ofs,
            hitdef->guard_damage_expr_count, hitdef->guard_damage);
        evaluated_hitdef.pause_p1 = eval_entity_time_expr(
            fight, attacker, cns, hitdef->pause_p1_expr_ofs,
            hitdef->pause_p1_expr_count, hitdef->pause_p1);
        evaluated_hitdef.pause_p2 = eval_entity_time_expr(
            fight, attacker, cns, hitdef->pause_p2_expr_ofs,
            hitdef->pause_p2_expr_count, hitdef->pause_p2);
        evaluated_hitdef.guard_velocity_x_q8 = eval_entity_q8_expr(
            fight, attacker, cns, hitdef->guard_velocity_x_expr_ofs,
            hitdef->guard_velocity_x_expr_count,
            hitdef->guard_velocity_x_q8);
        evaluated_hitdef.fall_x_velocity_q8 = eval_entity_q8_expr(
            fight, attacker, cns, hitdef->fall_x_velocity_expr_ofs,
            hitdef->fall_x_velocity_expr_count,
            hitdef->fall_x_velocity_q8);
        evaluated_hitdef.fall_y_velocity_q8 = eval_entity_q8_expr(
            fight, attacker, cns, hitdef->fall_y_velocity_expr_ofs,
            hitdef->fall_y_velocity_expr_count,
            hitdef->fall_y_velocity_q8);
        hitdef = &evaluated_hitdef;
    }

    ik_fighter_t* v = &fight->fighters[victim];
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
    attacker->hit_pause = hitdef->pause_p1;
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

    attacker->move_contact = 1u;
    ikf_credit_hit_power(
        fight, &fight->fighters[attacker->owner_player], v, hitdef, 1);

    int16_t state = 150;
    if (type == IK_CNS_STATE_CROUCH) state = 152;
    else if (type == IK_CNS_STATE_AIR) state = 154;

    const ik_cns_asset_t* victim_cns =
        cns_for_owner(fight, v->owner_player);
    if (ik_cns_find_state(victim_cns, state)) {
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)attacker->owner_player;
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, state);
    } else {
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)attacker->owner_player;
        v->ctrl = 0;
        ikf_enter_state_deferred(
            fight, v,
            type == IK_CNS_STATE_CROUCH ? 131 :
            type == IK_CNS_STATE_AIR ? 132 : 130);
    }

    ikf_queue_entity_hit_effect(
        fight, attacker, v, hitdef, hitdef->guard_spark_no, 0);
    ikf_queue_hitdef_sound(fight, 0, attacker, hitdef, 1);
    fight->events |= IK_EVENT_GUARD;
    if (guard_ko) {
        fight->winner = (uint8_t)(attacker->owner_player + 1u);
        fight->events |= IK_EVENT_KO;
        fight->win_by_ko = 1u;
        if (!ik_cns_find_state(victim_cns, 5050)) {
            v->cur_move_type = IK_CNS_MOVE_HIT;
            v->juggle_owner = (int8_t)attacker->owner_player;
            v->ctrl = 0;
            ikf_enter_state_deferred(fight, v, IK_STATE_KO);
            fight->round_over = 1;
            fight->events |= IK_EVENT_ROUND_OVER;
            fight->ko_freeze = IK_KO_FREEZE_FRAMES;
        }
    }
}

void ikf_apply_throw_from_entity(
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
    if (!attacker || attacker->type != IK_ENTITY_HELPER ||
        attacker->owner_player >= 2u) {
        return;
    }

    ik_fighter_t* v = &fight->fighters[victim];
    ikf_release_bound_target(fight, victim);
    ikf_release_entity_bound_fighter(fight, v);

    (void)ik_entity_add_target(
        fight->entities, attacker_handle,
        fight->player_entities[victim], hitdef->id);
    v->bound_to = -1;
    v->bound_entity = attacker_handle;
    v->last_hit_owner = (int8_t)attacker->owner_player;
    v->last_hit_id = hitdef->id;
    attacker->move_contact = 1u;
    ikf_credit_hit_power(
        fight, &fight->fighters[attacker->owner_player], v, hitdef, 0);
    record_entity_hit(fight, attacker);

    if (hitdef->p1_facing != 0) {
        const int attacker_x =
            ik_cns_q8_to_int(attacker->x_q8);
        const int8_t toward = v->x >= attacker_x ? 1 : -1;
        attacker->facing =
            hitdef->p1_facing > 0 ? toward : (int8_t)-toward;
    }
    if (hitdef->p2_facing != 0) {
        const int attacker_x =
            ik_cns_q8_to_int(attacker->x_q8);
        const int8_t toward = attacker_x >= v->x ? 1 : -1;
        v->facing =
            hitdef->p2_facing > 0 ? toward : (int8_t)-toward;
    }

    v->gethit_fall =
        (uint8_t)((hitdef->flags & IK_CNS_HITDEF_FALL) != 0u);
    const ik_cns_asset_t* attack_cns =
        cns_for_owner(fight, attacker->state_owner);
    v->gethit_fall_x_q8 = eval_entity_q8_expr(
        fight, attacker, attack_cns, hitdef->fall_x_velocity_expr_ofs,
        hitdef->fall_x_velocity_expr_count, hitdef->fall_x_velocity_q8);
    v->gethit_fall_y_q8 = eval_entity_q8_expr(
        fight, attacker, attack_cns, hitdef->fall_y_velocity_expr_ofs,
        hitdef->fall_y_velocity_expr_count, hitdef->fall_y_velocity_q8);
    v->gethit_fall_x_set = hitdef->fall_x_velocity_set;
    v->gethit_fall_recover = eval_entity_u8_expr(
        fight, attacker, attack_cns, hitdef->fall_recover_expr_ofs,
        hitdef->fall_recover_expr_count, hitdef->fall_recover);
    v->gethit_fall_recover_time = eval_entity_u8_expr(
        fight, attacker, attack_cns, hitdef->fall_recover_time_expr_ofs,
        hitdef->fall_recover_time_expr_count, hitdef->fall_recover_time);

    if (hitdef->p2_state_no >= 0) {
        v->state_owner = attacker->state_owner;
        v->cur_move_type = IK_CNS_MOVE_HIT;
        v->juggle_owner = (int8_t)attacker->owner_player;
        v->ctrl = 0;
        ikf_enter_state_deferred(fight, v, hitdef->p2_state_no);
    }
    if (hitdef->p1_state_no >= 0) {
        enter_entity_contact_state(
            fight, attacker_handle, hitdef->p1_state_no,
            p1_frames, p2_frames);
        attacker = ik_entity_get(
            fight->entities, attacker_handle);
        if (attacker) {
            int32_t priority = eval_entity_integer_expr(
                fight, attacker,
                cns_for_owner(fight, attacker->state_owner),
                hitdef->p1_spr_priority_expr_ofs,
                hitdef->p1_spr_priority_expr_count,
                hitdef->p1_spr_priority);
            if (priority >= INT8_MIN && priority <= INT8_MAX &&
                priority != -128) {
                attacker->spr_priority = (int8_t)priority;
            }
        }
    }

    attacker = ik_entity_get(fight->entities, attacker_handle);
    if (attacker) {
        ikf_queue_entity_hit_effect(
            fight, attacker, v, hitdef, hitdef->spark_no, 1);
    }
    ikf_queue_hitdef_sound(fight, 0, attacker, hitdef, 0);
    fight->events |= IK_EVENT_HIT;
    if (attacker && attacker->owner_player == 0u) ++fight->hits_p1;
    else ++fight->hits_p2;
}
