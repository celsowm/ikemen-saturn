#ifndef IKEMEN_FIGHT_HIT_VALUES_H
#define IKEMEN_FIGHT_HIT_VALUES_H

static inline int32_t ikf_scale_attack_damage(
    int32_t damage,
    int32_t attack_mul_q16
) {
    if (damage == 0 || attack_mul_q16 == 65536) return damage;
    const int64_t product = (int64_t)damage * attack_mul_q16;
    const int64_t rounded = product >= 0
        ? (product + 32768) / 65536
        : (product - 32768) / 65536;
    if (rounded > INT32_MAX) return INT32_MAX;
    if (rounded < INT32_MIN) return INT32_MIN;
    if (damage > 0 && rounded == 0 && attack_mul_q16 > 0) return 1;
    return (int32_t)rounded;
}

static inline uint8_t eval_fighter_time_expr(
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

static inline int32_t eval_fighter_integer_expr(
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

static inline int16_t eval_fighter_damage_expr(
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

static inline uint8_t eval_fighter_u8_expr(
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

static inline int16_t eval_fighter_q8_expr(
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

#endif
