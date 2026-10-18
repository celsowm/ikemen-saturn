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

/* Pinned Ikemen GO src/common.go Random(), with Schrage's 31-bit
 * Park-Miller calculation. The uint32_t state stores Go's int32 seed bits.
 * A 64-bit intermediate and explicit 32-bit wrap reproduce Go arithmetic,
 * including signed initial seeds; positive 1..IMax-1 is the normal cycle.
 * This does NOT reproduce the engine-global random-call schedule. */
int32_t ik_zss_ai_rng_next(uint32_t* state) {
    if (!state) return 0;
    const int64_t seed = (*state & UINT32_C(0x80000000))
        ? (int64_t)*state - INT64_C(4294967296) : (int64_t)*state;
    const int64_t w = seed / INT64_C(127773);
    const int64_t raw =
        (seed - w * INT64_C(127773)) * INT64_C(16807) -
        w * INT64_C(2836);
    const uint32_t wrapped = (uint32_t)raw;
    int64_t next = (wrapped & UINT32_C(0x80000000))
        ? (int64_t)wrapped - INT64_C(4294967296) : (int64_t)wrapped;
    if (next <= 0) {
        next += INT64_C(2147483647) - (next == 0 ? 1 : 0);
    }
    *state = (uint32_t)next;
    return (int32_t)next;
}

/* Pinned src/bytecode.go OC_random evaluates Rand(0, 999), not
 * Random()%1000. Integer division by IMax/1000 + 1 (=2147484) matches
 * the upstream inclusive ranged RNG, without floating-point drift. */
int32_t ik_zss_ai_random_trigger(uint32_t* state) {
    if (!state) return 0;
    return ik_zss_ai_rng_next(state) / INT32_C(2147484);
}

static uint16_t ai_roll(uint32_t* rng) {
    return (uint16_t)ik_zss_ai_random_trigger(rng);
}
static uint16_t ai_threshold(uint8_t level, uint16_t base) {
    return (uint16_t)(((uint32_t)base * level * level) / 48u);
}
static void ai_state(ik_fight_controls_t* out, int16_t state) {
    out->has_state_request = 1u;
    out->requested_state = state;
}

void ik_zss_ai_memory_step(const ik_fight_t* fight, uint8_t player,
                           ik_zss_ai_memory_t* memory) {
    if (!fight || player >= 2u || !memory) return;
    const ik_fighter_t* f = &fight->fighters[player];
    const ik_fighter_t* foe = &fight->fighters[player ^ 1u];
    /* Pinned AI.zss 25-27 runs before the global AI loop. */
    if (f->anim == 5120 || fight->round_state != 2u) {
        memory->gurt = 10u;
    }
    memory->aij = 0u; /* let AIJ, not a cross-frame map */
    memory->ai_ji = 0u;
    if (fight->round_state != 2u) return;
    /* Pinned AI.zss 73-76: take opponent's current hittime only when
     * the CPU controls its character and the target is helpless. */
    if (f->ctrl && !foe->ctrl && foe->hitstun > 0u) {
        memory->ai_ji = foe->hitstun;
    }
    /* Original AI.zss 483-486 decrements gurt on each active AI tick
     * before the subsequent jump declaration/cancellation predicates. */
    if (memory->gurt) --memory->gurt;
}

int ik_zss_ai_tick_memory(const ik_fight_t* fight, uint8_t player,
                          uint8_t level, uint32_t* rng,
                          ik_zss_ai_memory_t* memory,
                          ik_fight_controls_t* out) {
    if (!fight || !rng || !out || !memory || player >= 2u ||
        level == 0u || level > 8u) return 0;
    ik_zss_ai_memory_step(fight, player, memory);
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
    const int delta_y = (int)foe->y - f->y;
    const int neutral_ctrl = f->ctrl || f->state == 20 || f->state == 100;

    /* AI.zss post-contact branches. This bounded lowering uses the runtime's
     * actual hitstun and contact age in place of AI_JI, CC and juggle maps.
     * We do not claim matching upstream RNG or per-frame call ordering. */
    if (f->cur_state_type != IK_CNS_STATE_AIR &&
        f->move_contact && f->move_hit && foe->hp > 0 &&
        f->move_contact_time >= 1u && f->move_contact_time <= 3u &&
        f->hit_pause == 0u && foe->hitstun > 0u) {
        const int light = f->state == 200 || f->state == 230 ||
                          f->state == 400 || f->state == 430;
        const int heavy = f->state == 210 || f->state == 240 ||
                          f->state == 410;
        /* Super-finisher against a vulnerable opponent. */
        if ((light || (heavy && foe->hp < 350)) &&
            grounded && f->power >= 1000 &&
            dist >= -5 && dist <= 80 &&
            ai_roll(rng) < ai_threshold(level, 700u)) {
            ai_state(out, dist <= 25 ? 3050 : 3000);
            return 1;
        }
        /* Palm from midrange, Zankou at close range. */
        if (heavy && grounded && foe->hitstun > 9u &&
            dist >= 0 && dist <= 120 &&
            ai_roll(rng) < ai_threshold(level, 800u)) {
            ai_state(out, dist < 40 ? 1400 : dist < 85 ? 1010 : 1000);
            return 1;
        }
        /* Light-to-heavy confirm after the original hitpause. */
        if (light && grounded && foe->hitstun > 8u &&
            dist > 0 && dist < 60 &&
            ai_roll(rng) < ai_threshold(level, 600u)) {
            ai_state(out, dist < 35 ? 410 : 210);
            return 1;
        }
    }

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
                      dist > 70) || memory->ai_ji > 0u) ? 1 : 0;
    if (back_edge > 40 &&
        (foe_attacking ||
         (foe->cur_state_type != IK_CNS_STATE_LIEDOWN && dist < 30))) {
        direction = -1;
    }
    /* AI.zss lines 162-165: neutral close throw, before blocking and
     * the normal-attack family. The original uses map(AI_JI)<2; native
     * CPU lacks that persistent map, so do not throw while a previous
     * attack still reports contact. The current grounded/root, positive
     * distance, and idle/hit predicates make this an intentionally bounded
     * subset, not a 1:1 translation of the global State -1 loop.
     * The 310 gate is inclusive, exactly like the pinned ZSS predicate. */
    if (f->on_ground && neutral_ctrl &&
        f->cur_state_type == IK_CNS_STATE_STAND &&
        f->state != 100 && !f->move_contact &&
        grounded && !foe_hit &&
        dist >= 0 && dist < 30 &&
        ai_roll(rng) <= ai_threshold(level, 310u)) {
        ai_state(out, 800);
        return 1;
    }

    /* The AI.zss defensive block has a close parry option and a broader
     * guarding option. Using back delegates to the existing shared guard
     * state machine rather than inventing a second autoblock mechanism. */
    if (f->on_ground && neutral_ctrl &&
        f->cur_state_type == IK_CNS_STATE_STAND &&
        !foe_hit && foe_attacking && foe->state_time > 1u &&
        foe->cur_state_type != IK_CNS_STATE_LIEDOWN &&
        dist >= -20 && dist <= 75 &&
        f->state != 1300 && f->state != 1320 &&
        f->state != 1310 && f->state != 1330) {
        if (level > 4u && dist <= 30 && delta_y >= -50 &&
            delta_y <= 0 && ai_roll(rng) <= ai_threshold(level, 335u)) {
            ai_state(out, foe->cur_state_type == IK_CNS_STATE_CROUCH
                         ? 1320 : 1300);
            return 1;
        }
        if (f->in_guard_dist &&
            ai_roll(rng) <= ai_threshold(level, 700u)) {
            out->back = 1u;
            return 1;
        }
    }

    /* Source anti-air Upper family. Predictive opponent velocity history
     * is deferred; use conservative body and height ranges instead. */
    if (f->on_ground && neutral_ctrl &&
        f->cur_state_type == IK_CNS_STATE_STAND &&
        foe->cur_state_type == IK_CNS_STATE_AIR &&
        foe->state != 5040 && !foe_hit &&
        dist >= -20 && dist <= 50 &&
        delta_y >= -90 && delta_y <= -25 &&
        ai_roll(rng) <= ai_threshold(level, 450u)) {
        int16_t upper = 1100;
        if (f->power >= 500 && ai_roll(rng) % 3u == 1u) {
            upper = 1120;
        } else if ((int64_t)foe->vx_q8 * foe->facing > 0) {
            upper = 1110;
        }
        ai_state(out, upper);
        return 1;
    }

    /* AI.zss lines 155-158: anti-air normal in the ground neutral block.
     * Evaluate it only when the earlier Upper special was not selected;
     * unlike the Upper, its source roll uses the inclusive 420 factor.
     * No-juggle and opponent vertical-velocity prediction are only
     * conservatively approximated by a live airborne foe not in 5040.
     * This routes through the existing 410 CNS StateDef. */
    if (f->on_ground && neutral_ctrl &&
        f->cur_state_type == IK_CNS_STATE_STAND &&
        foe->cur_state_type == IK_CNS_STATE_AIR &&
        foe->state != 5040 && !foe_hit &&
        dist >= 0 && dist < 45 &&
        delta_y >= -70 && delta_y <= -20 &&
        ai_roll(rng) <= ai_threshold(level, 420u)) {
        ai_state(out, 410);
        return 1;
    }

    /* Original State -1 neutral block also runs in State 20 without Ctrl;
     * it may attack or declare a jump while the walk state owns input. */
    if ((!f->ctrl && f->state != 20) || !f->on_ground ||
        f->cur_state_type != IK_CNS_STATE_STAND ||
        f->cur_move_type == IK_CNS_MOVE_HIT) return 0;

    /* Grounded, non-juggle subset of the original light-attack clause.
     * Remaining AI_JI, get-up map, predicted velocity and juggle predicates
     * are deferred. At short range preserve the level-scaled random gate. */
    /* AI.zss 186-200: the grounded inner light branch selects
     * state 200 below 45px for a standing target, state 400 only below
     * 35px for a croucher. An outer 55px test cannot widen the inner
     * state-change gate. Source get-up map and AI_JI both gate lights. */
    if (memory->ai_ji == 0u && grounded && !foe_hit &&
        (memory->gurt == 0u || dist > 35) &&
        dist > -15 && dist < 45 &&
        (dist > 25 || ai_roll(rng) <= ai_threshold(level, 225u))) {
        if (foe->cur_state_type == IK_CNS_STATE_STAND) {
            ai_state(out, 200);
            return 1;
        }
        if (foe->cur_state_type == IK_CNS_STATE_CROUCH && dist < 35) {
            ai_state(out, 400);
            return 1;
        }
    }

    /* AI.zss 203-214: grounded heavy chooses 240, but its INNER
     * p2BodyDist x < 45 gate forbids 240 at 45..60px. IMPORTANT: the
     * OUTER random<=425 expression is still evaluated at 45..<60,
     * even when the following selection cannot fire. Keep this
     * otherwise-unused draw in source order before the poke lottery. */
    if (memory->ai_ji == 0u && grounded && !foe_hit &&
        dist >= 45 && dist < 60) {
        (void)ai_roll(rng);
    }

    /* AI.zss 230-242: medium-range poke lottery. Each random opcode
     * gets an independent original Rand(0,999) value. In the second
     * elseif, distance <=50 short-circuits BEFORE its random%4 call.
     * Standing fallback 440 is not available against a croucher. */
    if (grounded && !foe_hit && dist >= 45 && dist <= 60 &&
        ai_roll(rng) < ai_threshold(level, 250u)) {
        if (ai_roll(rng) % 4u == 0u) {
            ai_state(out, 210);
            return 1;
        }
        if (dist <= 50 && ai_roll(rng) % 4u == 1u) {
            ai_state(out, 240);
            return 1;
        }
        if (foe->cur_state_type == IK_CNS_STATE_STAND) {
            ai_state(out, 440);
            return 1;
        }
    }

    /* AI.zss lines 498-523: narrowly lowered jump declaration.
     * The original emits an RNG value before checking the wider state,
     * distance and edge predicates. In native we only evaluate that roll
     * for eligible 80..90px grounded neutral encounters, because the
     * global GO random call schedule and the full AI_JI variables are missing.
     * At a safe distance the original jump requires either the opponent
     * attacking (level > 6), or our front edge < 50px plus a 375-scaled
     * roll. The latter is an intentionally narrower source-backed case.
     * Both paths preserve the original Rand(0,999) draw even if an
     * attacking opponent grants the unconditional level>6 alternative.
     * Native requests actual CNS State 40; it does not invent a jump arc.
     */
    if (f->on_ground && (f->ctrl || f->state == 20) &&
        (f->state == 0 || f->state == 20) &&
        f->cur_state_type == IK_CNS_STATE_STAND &&
        f->cur_move_type != IK_CNS_MOVE_HIT &&
        !foe_hit && grounded && dist >= 80 && dist <= 90 &&
        memory->gurt == 0u && f->prev_state != 5120) {
        const int bounds_known = f->xmin_q8 < f->xmax_q8 &&
            f->x_q8 >= f->xmin_q8 && f->x_q8 <= f->xmax_q8;
        const int front_edge = (int)((f->facing >= 0
            ? f->xmax_q8 - f->x_q8 : f->x_q8 - f->xmin_q8) /
            IK_CNS_Q8_ONE) - f->push_front;
        const int close_to_front_edge = bounds_known && front_edge < 50;
        if (close_to_front_edge || (foe_attacking && level > 6u)) {
            const uint16_t roll = ai_roll(rng);
            if ((close_to_front_edge &&
                 roll < ai_threshold(level, 375u)) ||
                (foe_attacking && level > 6u)) {
                memory->aij = 1u;
                ai_state(out, 40);
                out->forward = 1u;
                return 1;
            }
        }
    }

    /* AI.zss lines 539-542: reactive backward dash after earlier
     * anti-air/attack/jump decisions. This bounded translation handles
     * the first opponent-attack branch, not the opponent's get-up branch.
     * The source uses an inclusive 296-scaled random threshold and requires
     * >40px free behind the fighter. CNS state 105 owns its physics. */
    if (f->on_ground && (f->ctrl || f->state == 20) &&
        f->cur_state_type != IK_CNS_STATE_AIR &&
        !foe_hit && foe_attacking && dist >= 0 && dist < 55 &&
        back_edge > 40 &&
        ai_roll(rng) <= ai_threshold(level, 296u)) {
        ai_state(out, 105);
        return 1;
    }

    /* The original AI.zss evaluates neutral attacks even when the character
     * is walking in State 20. Walking direction is a fallback only. Evaluating
     * it first trapped the CPU in a 25-30px spacing oscillation forever. */
    if (f->state == 20) {
        if (direction == 0) {
            ai_state(out, 0);
        } else {
            out->forward = (uint8_t)(direction > 0);
            out->back = (uint8_t)(direction < 0);
        }
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


/* Existing stateless API retained for isolated host tests and consumers.
 * The integrated ik_frame_step uses ik_zss_ai_tick_memory instead. */
int ik_zss_ai_tick(const ik_fight_t* fight, uint8_t player,
                   uint8_t level, uint32_t* rng, ik_fight_controls_t* out) {
    ik_zss_ai_memory_t local = {0};
    return ik_zss_ai_tick_memory(
        fight, player, level, rng, &local, out);
}
