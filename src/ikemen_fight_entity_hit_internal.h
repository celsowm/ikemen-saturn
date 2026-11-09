#ifndef IKEMEN_FIGHT_ENTITY_HIT_INTERNAL_H
#define IKEMEN_FIGHT_ENTITY_HIT_INTERNAL_H

static inline uint8_t eval_entity_time_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    uint8_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_entity_expr(
            fight, entity, cns, offset, count, &value)) {
        return fallback;
    }
    if (value < 0) return 0u;
    if (value > UINT8_MAX) return UINT8_MAX;
    return (uint8_t)value;
}

static inline int32_t eval_entity_integer_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int32_t fallback
) {
    int32_t value = 0;
    return count && ikf_eval_cns_entity_expr(
        fight, entity, cns, offset, count, &value) ? value : fallback;
}

static inline int16_t eval_entity_damage_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int16_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_entity_expr(
            fight, entity, cns, offset, count, &value)) {
        return fallback;
    }
    if (value < INT16_MIN) return INT16_MIN;
    if (value > INT16_MAX) return INT16_MAX;
    return (int16_t)value;
}

static inline uint8_t eval_entity_u8_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    uint8_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_entity_expr(
            fight, entity, cns, offset, count, &value)) return fallback;
    if (value < 0) return 0u;
    if (value > UINT8_MAX) return UINT8_MAX;
    return (uint8_t)value;
}

static inline int16_t eval_entity_q8_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int16_t fallback
) {
    int32_t value = 0;
    if (!count || !ikf_eval_cns_entity_expr(
            fight, entity, cns, offset, count, &value)) return fallback;
    value /= 256;
    if (value < INT16_MIN) return INT16_MIN;
    if (value > INT16_MAX) return INT16_MAX;
    return (int16_t)value;
}

static inline void record_entity_hit(ik_fight_t* fight, ik_entity_t* attacker) {
    if (!fight || !attacker) return;
    attacker->move_hit = 1u;
    if (attacker->owner_player < 2u) {
        ikf_record_hit(
            &fight->fighters[attacker->owner_player],
            (uint8_t)(attacker->owner_player ^ 1u));
    }
}

static inline void enter_entity_contact_state(
    ik_fight_t* fight,
    ik_entity_handle_t handle,
    int32_t state,
    const ik_frame_table_t* p1_frames,
    const ik_frame_table_t* p2_frames
) {
    if (!fight || !fight->entities) return;
    ik_entity_runtime_t runtime;
    ik_entity_runtime_init(
        &runtime, fight->entities, fight->cns,
        p1_frames, p2_frames);
    ikf_configure_fight_entity_runtime(fight, &runtime);
    (void)ik_entity_runtime_enter_state(&runtime, handle, state);
}

#endif
