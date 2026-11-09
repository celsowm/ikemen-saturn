/* Sound and effect events queued for the presentation layer. */
#include "ikemen_fight_internal.h"

void ikf_queue_sound_event(
    ik_fight_t* fight,
    int16_t group,
    int16_t item
) {
    if (!fight || group < 0 || item < 0 ||
        fight->sound_count >= IK_MAX_SOUND_EVENTS) {
        return;
    }
    ik_sound_event_t* event =
        &fight->sound_events[fight->sound_count++];
    event->group = group;
    event->item = item;
}

void ikf_queue_reversal_effect(
    ik_fight_t* fight,
    const ik_fighter_t* defender,
    const ik_cns_reversaldef_t* reversal
) {
    if (!fight || !defender || !reversal || reversal->spark_no < 0 ||
        fight->effect_count >= IK_MAX_EFFECT_EVENTS) {
        return;
    }
    ik_effect_event_t* effect =
        &fight->effect_events[fight->effect_count++];
    effect->action = reversal->spark_no;
    effect->x = (int16_t)(
        defender->x + (int16_t)defender->facing * reversal->spark_x);
    effect->y = (int16_t)(defender->y + reversal->spark_y);
}

static int16_t hitdef_spark_value(
    const ik_fight_t* fight,
    const ik_fighter_t* attacker,
    const ik_entity_t* entity,
    uint16_t offset,
    uint8_t count,
    int16_t fallback
) {
    int32_t value = 0;
    const ik_cns_asset_t* cns = entity
        ? cns_for_owner(fight, entity->state_owner)
        : cns_for_fighter(fight, attacker);
    const int ok = entity
        ? ikf_eval_cns_entity_expr(fight, entity, cns, offset, count, &value)
        : ikf_eval_cns_expr(fight, attacker, cns, offset, count, &value);
    if (!count || !ok) return fallback;
    if (value < INT16_MIN) return INT16_MIN;
    if (value > INT16_MAX) return INT16_MAX;
    return (int16_t)value;
}

void ikf_queue_hitdef_sound(
    ik_fight_t* fight,
    const ik_fighter_t* attacker,
    const ik_entity_t* entity,
    const ik_cns_hitdef_t* hitdef,
    int guarded
) {
    if (!fight || !hitdef) return;
    const uint16_t group_ofs = guarded
        ? hitdef->guard_sound_group_expr_ofs
        : hitdef->hit_sound_group_expr_ofs;
    const uint8_t group_count = guarded
        ? hitdef->guard_sound_group_expr_count
        : hitdef->hit_sound_group_expr_count;
    const uint16_t item_ofs = guarded
        ? hitdef->guard_sound_item_expr_ofs
        : hitdef->hit_sound_item_expr_ofs;
    const uint8_t item_count = guarded
        ? hitdef->guard_sound_item_expr_count
        : hitdef->hit_sound_item_expr_count;
    const int16_t fallback_group = guarded
        ? hitdef->guard_sound_group : hitdef->hit_sound_group;
    const int16_t fallback_item = guarded
        ? hitdef->guard_sound_item : hitdef->hit_sound_item;
    const int16_t group = hitdef_spark_value(
        fight, attacker, entity, group_ofs, group_count,
        fallback_group);
    const int16_t item = hitdef_spark_value(
        fight, attacker, entity, item_ofs, item_count,
        fallback_item);
    ikf_queue_sound_event(fight, group, item);
}

void ikf_queue_hit_effect(ik_fight_t* fight,
                             const ik_fighter_t* attacker,
                             const ik_fighter_t* victim,
                             const ik_cns_hitdef_t* hitdef,
                             int16_t action,
                             int use_trigger2_y) {
    (void)action;
    if (!fight || !attacker || !victim || !hitdef ||
        fight->effect_count >= IK_MAX_EFFECT_EVENTS) return;
    const int guarded = !use_trigger2_y;
    const int16_t resolved_action = guarded
        ? hitdef_spark_value(
            fight, attacker, 0, hitdef->guard_spark_no_expr_ofs,
            hitdef->guard_spark_no_expr_count, hitdef->guard_spark_no)
        : hitdef_spark_value(
            fight, attacker, 0, hitdef->spark_no_expr_ofs,
            hitdef->spark_no_expr_count, hitdef->spark_no);
    if (resolved_action < 0) return;
    ik_effect_event_t* effect =
        &fight->effect_events[fight->effect_count++];
    effect->action = resolved_action;
    const int16_t spark_x = hitdef_spark_value(
        fight, attacker, 0, hitdef->spark_x_expr_ofs,
        hitdef->spark_x_expr_count, hitdef->spark_x);
    effect->x = (int16_t)(
        victim->x + (int16_t)attacker->facing * spark_x);
    /* MUGEN sparkxy: X is relative to P2, Y is relative to P1. Fast Upper
     * reuses one HitDef through trigger2 and supplies a second spark Y. */
    const int16_t spark_y =
        use_trigger2_y && attacker->active_hitdef_secondary &&
        hitdef->has_trigger2
            ? hitdef_spark_value(
                fight, attacker, 0,
                hitdef->trigger2_spark_y_expr_ofs,
                hitdef->trigger2_spark_y_expr_count,
                hitdef->trigger2_spark_y)
            : hitdef_spark_value(
                fight, attacker, 0, hitdef->spark_y_expr_ofs,
                hitdef->spark_y_expr_count, hitdef->spark_y);
    effect->y = (int16_t)(attacker->y + spark_y);
}

void ikf_queue_entity_hit_effect(
    ik_fight_t* fight,
    const ik_entity_t* attacker,
    const ik_fighter_t* victim,
    const ik_cns_hitdef_t* hitdef,
    int16_t action,
    int use_trigger2_y
) {
    (void)action;
    if (!fight || !attacker || !victim || !hitdef ||
        fight->effect_count >= IK_MAX_EFFECT_EVENTS) {
        return;
    }
    const int guarded = !use_trigger2_y;
    const int16_t resolved_action = guarded
        ? hitdef_spark_value(
            fight, 0, attacker, hitdef->guard_spark_no_expr_ofs,
            hitdef->guard_spark_no_expr_count, hitdef->guard_spark_no)
        : hitdef_spark_value(
            fight, 0, attacker, hitdef->spark_no_expr_ofs,
            hitdef->spark_no_expr_count, hitdef->spark_no);
    if (resolved_action < 0) return;
    ik_effect_event_t* effect =
        &fight->effect_events[fight->effect_count++];
    effect->action = resolved_action;
    const int16_t spark_x = hitdef_spark_value(
        fight, 0, attacker, hitdef->spark_x_expr_ofs,
        hitdef->spark_x_expr_count, hitdef->spark_x);
    effect->x = (int16_t)(
        victim->x + (int16_t)attacker->facing * spark_x);
    const int16_t spark_y =
        use_trigger2_y && attacker->active_hitdef_secondary &&
        hitdef->has_trigger2
            ? hitdef_spark_value(
                fight, 0, attacker,
                hitdef->trigger2_spark_y_expr_ofs,
                hitdef->trigger2_spark_y_expr_count,
                hitdef->trigger2_spark_y)
            : hitdef_spark_value(
                fight, 0, attacker, hitdef->spark_y_expr_ofs,
                hitdef->spark_y_expr_count, hitdef->spark_y);
    effect->y = (int16_t)(
        ik_cns_q8_to_int(attacker->y_q8) + spark_y);
}
