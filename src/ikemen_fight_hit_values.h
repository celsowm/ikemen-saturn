#ifndef IKEMEN_FIGHT_HIT_VALUES_H
#define IKEMEN_FIGHT_HIT_VALUES_H

static inline int32_t ikf_scale_character_damage(
    int32_t damage,
    int32_t attack_mul_q16,
    const ik_cns_constants_t* attacker_constants,
    const ik_cns_constants_t* defender_constants,
    int32_t custom_defense_q16
) {
    if (damage == 0) return damage;
    const int32_t attack = attacker_constants &&
        attacker_constants->attack > 0
            ? attacker_constants->attack : 100;
    const int32_t defence = defender_constants &&
        defender_constants->defence > 0
            ? defender_constants->defence : 100;
    if (custom_defense_q16 <= 0) custom_defense_q16 = 65536;
    int64_t multiplier_q16 =
        (int64_t)attack * attack_mul_q16 * 65536 /
        ((int64_t)defence * custom_defense_q16);
    if (multiplier_q16 > INT32_MAX) multiplier_q16 = INT32_MAX;
    if (multiplier_q16 < INT32_MIN) multiplier_q16 = INT32_MIN;
    const int64_t product = (int64_t)damage * multiplier_q16;
    const int64_t rounded = product >= 0
        ? (product + 32768) / 65536
        : (product - 32768) / 65536;
    if (rounded > INT32_MAX) return INT32_MAX;
    if (rounded < INT32_MIN) return INT32_MIN;
    if (damage > 0 && rounded == 0 && multiplier_q16 > 0) return 1;
    return (int32_t)rounded;
}

static inline int32_t ikf_active_custom_defense_q16(
    const ik_fighter_t* fighter
) {
    if (!fighter ||
        (fighter->defense_mul_delay &&
         fighter->cur_move_type != IK_CNS_MOVE_HIT) ||
        fighter->custom_defense_q16 <= 0) {
        return 65536;
    }
    return fighter->custom_defense_q16;
}

static inline int32_t ikf_scale_life_add(
    int64_t amount_q16,
    const ik_cns_constants_t* constants,
    int32_t custom_defense_q16,
    int absolute
) {
    if (custom_defense_q16 <= 0) custom_defense_q16 = 65536;
    int64_t adjusted_q16 = amount_q16;
    if (!absolute) {
        const int32_t defence = constants && constants->defence > 0
            ? constants->defence : 100;
        adjusted_q16 = amount_q16 * 100 * 65536 /
            ((int64_t)defence * custom_defense_q16);
    }
    if (!absolute && adjusted_q16 < 0 && adjusted_q16 > -65536) {
        return -1;
    }
    const int64_t rounded = adjusted_q16 >= 0
        ? (adjusted_q16 + 32768) / 65536
        : (adjusted_q16 - 32768) / 65536;
    if (rounded > INT32_MAX) return INT32_MAX;
    if (rounded < INT32_MIN) return INT32_MIN;
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
