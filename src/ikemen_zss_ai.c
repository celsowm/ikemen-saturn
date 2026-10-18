#include "ikemen_zss_ai.h"
/* AI.zss State -1: knee follow-up, verbatim condition from lines 429-434.
 * Source drift is rejected by the KFM ZSS asset compiler.
 */
int ik_zss_ai_request(const ik_fight_t* fight, uint8_t player,
                      uint8_t level, int16_t* destination) {
    if (!fight || !destination || player >= 2u || level < 1u ||
        level > 8u || fight->round_state != 2u) return 0;
    const ik_fighter_t* f = &fight->fighters[player];
    if ((f->state != 1051 && f->state != 1061 && f->state != 1071) ||
        f->vy_q8 >= -IK_CNS_Q8_ONE ||
        (!f->move_hit && !(f->move_contact && level < 6u))) return 0;
    *destination = f->state == 1071 ? 1075 : 1055;
    return 1;
}

/* Bounded source-informed subset of AI.zss neutral movement and grounded
 * lights. Its RNG and evaluation order are NOT upstream Ikemen GO's.
 * Source drift of the translated movement branches fails asset generation.
 */
static uint16_t ai_roll(uint32_t* rng) {
    *rng = *rng * UINT32_C(1664525) + UINT32_C(1013904223);
    return (uint16_t)((*rng >> 8) % 1000u);
}
static uint16_t ai_threshold(uint8_t level, uint16_t base) {
    return (uint16_t)(((uint32_t)base * level * level) / 48u);
}
static void ai_state(ik_fight_controls_t* out, int16_t state) {
    out->has_state_request = 1u;
    out->requested_state = state;
}

int ik_zss_ai_tick(const ik_fight_t* fight, uint8_t player,
                   uint8_t level, uint32_t* rng, ik_fight_controls_t* out) {
    if (!fight || !rng || !out || player >= 2u ||
        level == 0u || level > 8u) return 0;
    const ik_fighter_t* f = &fight->fighters[player];
    const ik_fighter_t* foe = &fight->fighters[player ^ 1u];

    if (fight->round_state != 2u) {
        /* AI.zss -4: reset run on intro/outro. */
        if (f->state == 100) {
            ai_state(out, 0);
            return 1;
        }
        return 0;
    }
    /* The already validated knee follow-up has priority over neutral AI. */
    if (ik_zss_ai_request(fight, player, level, &out->requested_state)) {
        out->has_state_request = 1u;
        return 1;
    }
    if (f->hp <= 0 || foe->hp <= 0 || f->hit_pause != 0u) return 0;

    /* Mirrors ikf_body_dist_x from the shared fight geometry. */
    const int dist = ((int)foe->x - f->x) * f->facing -
                     f->push_front - foe->push_front;
    const int back_edge = (int)((f->facing >= 0
        ? f->x_q8 - f->xmin_q8
        : f->xmax_q8 - f->x_q8) / IK_CNS_Q8_ONE) - f->push_back;
    const int grounded = foe->cur_state_type == IK_CNS_STATE_STAND ||
                         foe->cur_state_type == IK_CNS_STATE_CROUCH;
    const int foe_attacking = foe->cur_move_type == IK_CNS_MOVE_ATTACK;
    const int foe_hit = foe->cur_move_type == IK_CNS_MOVE_HIT;

    if (f->state == 100) {
        /* Original run-stop distance and cross-up checks. */
        if ((dist < (grounded ? 40 : 20) && foe->state != 5040) ||
            dist < -65) {
            ai_state(out, 0);
            return 1;
        }
        return 0;
    }
    /* AI.zss AIw map: forward unless the foe is attacking/very close;
     * retreat only with sufficient space behind the player. AI_JI omitted. */
    int direction = (!foe_attacking || dist > 25 ||
                     (foe->cur_state_type == IK_CNS_STATE_LIEDOWN &&
                      dist > 70)) ? 1 : 0;
    if (back_edge > 40 &&
        (foe_attacking ||
         (foe->cur_state_type != IK_CNS_STATE_LIEDOWN && dist < 30))) {
        direction = -1;
    }
    if (f->state == 20) {
        if (direction == 0) {
            ai_state(out, 0);
        } else {
            /* Hybrid common state 20 uses direction buttons, not map(AIw). */
            out->forward = (uint8_t)(direction > 0);
            out->back = (uint8_t)(direction < 0);
        }
        return 1;
    }
    if (!f->ctrl || !f->on_ground ||
        f->cur_state_type != IK_CNS_STATE_STAND ||
        f->cur_move_type == IK_CNS_MOVE_HIT) return 0;

    /* Grounded, non-juggle subset of the original light-attack clause.
     * Remaining AI_JI, get-up map, predicted velocity and juggle predicates
     * are deferred. At short range preserve the level-scaled random gate. */
    if (grounded && !foe_hit && dist > -15 && dist < 45 &&
        (dist > 25 || ai_roll(rng) <= ai_threshold(level, 225u))) {
        ai_state(out, foe->cur_state_type == IK_CNS_STATE_CROUCH ? 400 : 200);
        return 1;
    }
    /* Original run probability when the foe is far and not attacking.
     * The hitfall/5300 chase alternative is not yet handled. */
    if (dist >= 120 && (!foe_attacking || back_edge < 40) &&
        ai_roll(rng) <= ai_threshold(level, 396u)) {
        ai_state(out, 100);
        return 1;
    }
    if (direction != 0 && dist >= 25 && dist <= 120 &&
        (!foe_attacking || back_edge < 40) && ai_roll(rng) < 249u) {
        out->forward = (uint8_t)(direction > 0);
        out->back = (uint8_t)(direction < 0);
        ai_state(out, 20);
        return 1;
    }
    return 0;
}
