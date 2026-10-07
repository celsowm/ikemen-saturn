/* Frame orchestration: pause, round timer, KO and fight update. */
#include "ikemen_fight_internal.h"

typedef struct ik_frame_inputs {
    const ik_fight_controls_t* controls[2];
    const ik_frame_table_t* frames[2];
} ik_frame_inputs_t;

static void select_match_over_defeat_anim(
    ik_fighter_t* fighter,
    const ik_frame_table_t* frames
) {
    if (!fighter || !frames || fighter->state != 5150 ||
        fighter->anim < 5140 || fighter->anim > 5149) {
        return;
    }

    const int16_t match_anim = (int16_t)(fighter->anim + 10);
    uint32_t first = 0u;
    uint32_t count = 0u;
    if (!ik_frames_bounds(frames, match_anim, &first, &count) ||
        count == 0u) {
        return;
    }

    fighter->anim = match_anim;
    fighter->anim_time = 0u;
}

static void begin_frame(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in
) {
    fight->player_frames[0] = in->frames[0];
    fight->player_frames[1] = in->frames[1];
    fight->effect_count = 0u;
    fight->sound_count = 0u;
    fight->events = IK_EVENT_NONE;
    fight->intro_asserted = 0u;
    ikf_advance_projectile_query_times(fight);
}

/* One entity-runtime pass with this frame's command masks. */
static void step_entities(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in,
    int paused
) {
    if (!fight->entities) return;
    ikf_sync_player_entities(fight);
    ik_entity_runtime_t runtime;
    ik_entity_runtime_init(
        &runtime, fight->entities, fight->cns,
        in->frames[0], in->frames[1]);
    ikf_configure_fight_entity_runtime(fight, &runtime);
    ik_entity_runtime_set_command_mask(
        &runtime, 0u, controls_command_mask(in->controls[0]));
    ik_entity_runtime_set_command_mask(
        &runtime, 1u, controls_command_mask(in->controls[1]));

    if (!paused) {
        ik_entity_runtime_step(&runtime);
        return;
    }
    /* Entity pause/super-move budgets are independent from the fighter's
     * movetime. Both players' dynamic entities get a chance to consume their
     * authored budget during any pause. */
    ik_entity_runtime_step_paused(
        &runtime, 0u, fight->pause_is_super != 0u);
    ik_entity_runtime_step_paused(
        &runtime, 1u, fight->pause_is_super != 0u);
}

/* Round-over screen: hold until START (after the KO freeze) resets. */
static void update_round_over(
    ik_fight_t* fight,
    const ik_fight_controls_t* p1
) {
    if (p1 && p1->start && fight->ko_freeze == 0u) {
        ik_fight_reset(fight);
        return;
    }
    if (fight->ko_freeze > 0u) fight->ko_freeze--;
    fight->frame++;
}

/* After hit detection, paused or not: upstream drops a fighter that is not
 * in MoveType H (or is KO'd) from its attackers' target lists. A reversed
 * attacker is spared for one tick (hittmp = -1). */
static void exit_targets(ik_fight_t* fight) {
    for (int i = 0; i < 2; ++i) {
        ik_fighter_t* f = &fight->fighters[i];

        if (!f->reversed &&
            (f->cur_move_type != IK_CNS_MOVE_HIT || f->state == 5150)) {
            ikf_exit_target(fight, f);
        }
        /* The attacker's own list (upstream dropTargets). */
        if (f->drop_target_skip > 0u) {
            --f->drop_target_skip;
        } else if (f->target_index >= 0 && f->target_index < 2 &&
                   fight->fighters[(int)f->target_index].cur_move_type !=
                       IK_CNS_MOVE_HIT) {
            f->target_index = -1;
            f->target_id = -1;
        }
    }
}

static void release_pause_if_done(ik_fight_t* fight) {
    --fight->pause_time;
    if (fight->pause_time != 0u) return;
    fight->pause_owner = -1;
    fight->pause_move_time = 0u;
    fight->pause_end_cmd_buffer_time = 0u;
    fight->pause_is_super = 0u;
}

/* Pause/SuperPause: only the pause owner (while its movetime lasts) and the
 * entities with their own budgets act. */
static void update_paused(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in
) {
    const int owner =
        fight->pause_owner >= 0 && fight->pause_owner < 2
            ? fight->pause_owner : -1;

    if (fight->pause_move_time > 0u && owner >= 0) {
        ikf_step_fighter(
            fight, owner, in->controls[owner],
            owner == 1 && in->controls[1] == 0,
            in->frames[owner], in->frames[owner ^ 1]);
        ikf_resolve_paused_owner_contact(
            fight, owner, in->controls[0], in->controls[1],
            in->frames[0], in->frames[1]);
        ikf_camera_step(fight);
        ikf_finish_tick(fight);
        --fight->pause_move_time;
    }

    if (fight->entities) {
        step_entities(fight, in, 1);
        if (!fight->round_over) {
            ikf_resolve_projectile_trades(fight, in->frames[0], in->frames[1]);
            ikf_resolve_entity_contacts(
                fight, in->controls[0], in->controls[1],
                in->frames[0], in->frames[1], -1);
        }
    }

    exit_targets(fight);
    release_pause_if_done(fight);
    fight->frame++;
}

/* Step the active-round clock. A timeout is a round-end decision, not an
 * immediate freeze: upstream enters the same RoundState 3/4 outro machinery
 * (without KO slow motion), keeps characters ticking, then dispatches
 * win/lose/draw poses. */
static void tick_round_timer(ik_fight_t* fight) {
    if (fight->round_state != 2u) return;

    /* Upstream decrements curRoundTime in stepRoundState(), but roundState()
     * remains 2 on the rendered frame that reaches zero because sys.intro is
     * still 0. The timeout decision becomes visible as RoundState 3 on the
     * following tick, when the post-round path decrements intro below zero. */
    if (fight->timer_frames > 0u) {
        --fight->timer_frames;
        return;
    }

    const int p1 = fight->fighters[0].hp;
    const int p2 = fight->fighters[1].hp;
    fight->winner = p1 == p2 ? 0u : (uint8_t)(p1 > p2 ? 1u : 2u);
    fight->round_state = 3u;
    fight->round_outro_ticks = 0u;
    fight->ko_slow_ticks = 0u;
    fight->ko_speed_accum_q16 = 0u;
    fight->ko_tick_frame_pending = 0u;
    fight->events |= IK_EVENT_ROUND_OVER;
}

static void advance_round_state(ik_fight_t* fight) {
    if (fight->round_state == 0u) {
        /* Give RoundState=0 one authored pre-intro tick, then let the
         * character's AssertSpecial Intro controller hold the intro. */
        fight->round_state = 1u;
    } else if (fight->round_state == 1u && !fight->intro_asserted) {
        if (++fight->round_wait >= IK_ROUND_FIGHT_WAIT_TICKS) {
            fight->round_state = 2u;
        }
    }
}

/* Projectile-vs-projectile cancellation happens first. Surviving
 * player/helper/projectile attacks then enter one deterministic
 * gather/arbitrate/apply queue, so priority and Hit/Miss/Dodge semantics are
 * not split by attacker representation. */
static void resolve_contacts(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in
) {
    if (fight->round_over) return;
    ikf_resolve_projectile_trades(fight, in->frames[0], in->frames[1]);
    ikf_resolve_global_contacts(
        fight, in->controls[0], in->controls[1],
        in->frames[0], in->frames[1]);
}

/* HitDef controllers belong to tickFrame, while slowed KO collision is
 * resolved at tickNextFrame. Refresh the root fighters' active HitDefs here
 * so a freshly executed HitDef clears its target list on the controller tick
 * without being allowed to collide until the next-frame phase. */
static void refresh_root_hitdefs(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in
) {
    for (int atk = 0; atk < 2; ++atk) {
        ik_fighter_t* attacker = &fight->fighters[atk];
        const ik_fighter_t* victim = &fight->fighters[atk ^ 1];
        const ik_frame_table_t* frames = frames_for_fighter(fight, attacker);
        if (!frames) frames = in->frames[atk];
        uint8_t local = 0u;
        (void)ikf_active_hitdef(fight, frames, attacker, victim, &local);
    }
}

static void check_knockout(
    ik_fight_t* fight,
    const ik_frame_inputs_t* in
) {
    if (fight->round_over) return;

    /* Ikemen decides the KO as soon as life reaches zero. 5150 is only the
     * later lying-defeated common state; waiting for it kept RoundState at 2
     * for the whole fall and then froze simulation at exactly the wrong time. */
    if (fight->round_state == 2u) {
        const int p1_dead = fight->fighters[0].hp <= 0;
        const int p2_dead = fight->fighters[1].hp <= 0;
        if (p1_dead || p2_dead) {
            fight->round_state = 3u;
            fight->winner =
                p1_dead == p2_dead ? 0u : (uint8_t)(p1_dead ? 2u : 1u);
            /* Upstream consumes the first slow-time tick on the KO frame when
             * it selects turbo for the following rendered frame. */
            fight->ko_slow_ticks =
                IK_ROUND_SLOW_TIME > 0u ? IK_ROUND_SLOW_TIME - 1u : 0u;
            /* advance_outro_state() below accounts for the KO frame's
             * intro transition from 0 to -1. */
            fight->round_outro_ticks = 0u;
            /* The KO transition frame still runs at the old 1.0 speed.
             * That end-of-frame step schedules one final tickFrame for the
             * next render. After that, round.slow.speed owns the fractional
             * clock and tickNextFrame trails tickFrame independently. */
            fight->ko_speed_accum_q16 = 0u;
            fight->ko_current_speed_q16 = IK_ROUND_SLOW_SPEED_Q16;
            fight->ko_tick_frame_pending = 1u;
            fight->events |= IK_EVENT_KO;
        }
    }

    /* MatchOver may become true while the defeated fighter is already in
     * 5150. Keep the existing authored 5140 -> 5150-family selection alive
     * instead of using 5150 as the KO trigger. */
    if (fight->round_state >= 3u) {
        for (int i = 0; i < 2; ++i) {
            if (fight->round_outro_ticks >= IK_ROUND_OVER_HIT_TIME &&
                fight->fighters[i].hp <= 0 &&
                fight->fighters[i].state == 5150) {
                select_match_over_defeat_anim(
                    &fight->fighters[i], in->frames[i]);
            }
        }
    }
}

/* Return non-zero on rendered frames that advance one logical game tick.
 * This mirrors Ikemen's KO turbo: 0.25 for the first 15 slow ticks, then a
 * linear fade to 1.0 over the remaining 45. */
typedef struct ik_ko_phase {
    uint8_t tick_frame;
    uint8_t tick_next_frame;
} ik_ko_phase_t;

static uint32_t ko_speed_q16(const ik_fight_t* fight) {
    if (!fight || fight->ko_slow_ticks == 0u) return 65536u;

    uint32_t speed_q16 = IK_ROUND_SLOW_SPEED_Q16;
    if (fight->ko_slow_ticks < IK_ROUND_SLOW_FADE_TIME) {
        const uint32_t elapsed =
            IK_ROUND_SLOW_FADE_TIME - fight->ko_slow_ticks;
        const uint32_t range = 65536u - IK_ROUND_SLOW_SPEED_Q16;
        speed_q16 +=
            (range * elapsed) / IK_ROUND_SLOW_FADE_TIME;
    }
    return speed_q16;
}

/* Ikemen has two related clocks while turbo < 1:
 *   tickFrame     -> state/controllers/physics
 *   tickNextFrame -> Animation.Action(), HitPause and end-of-frame clocks
 *
 * At 0.25x a KO therefore looks like:
 *   tickFrame, --, --, tickNextFrame, tickFrame, --, --, tickNextFrame...
 * The KO transition frame itself already consumed the first slow-time count
 * and scheduled the first tickFrame for the following render. */
static ik_ko_phase_t ko_phase_advance(ik_fight_t* fight) {
    ik_ko_phase_t phase = {1u, 1u};
    if (!fight || fight->round_state < 3u || fight->ko_slow_ticks == 0u) {
        return phase;
    }

    const uint32_t speed_q16 = fight->ko_current_speed_q16;
    phase.tick_frame = fight->ko_tick_frame_pending;
    phase.tick_next_frame =
        fight->ko_speed_accum_q16 + speed_q16 >= 65536u;

    uint32_t accum = fight->ko_speed_accum_q16 + speed_q16;
    fight->ko_tick_frame_pending = 0u;
    if (accum >= 65536u) {
        accum -= 65536u;
        fight->ko_tick_frame_pending = 1u;
    }
    fight->ko_speed_accum_q16 = accum;

    /* gameFrame() advances with the speed selected on the PREVIOUS
     * tickNextFrame. Ikemen computes the next turbo only at the boundary,
     * before decrementing slowtime, then holds that value for every rendered
     * frame until the next boundary. Recomputing from slowtime every render
     * makes the fade run early. */
    if (phase.tick_next_frame && fight->ko_slow_ticks > 0u) {
        fight->ko_current_speed_q16 = ko_speed_q16(fight);
        --fight->ko_slow_ticks;
    }
    return phase;
}

static int fighter_ready_for_round4(const ik_fighter_t* fighter) {
    if (!fighter) return 1;

    /* Ikemen's SCF_over_ko is set when the root reaches common state 5150.
     * Such a defeated fighter no longer blocks the RoundState 4 gate. */
    if (fighter->state == 5150) return 1;

    /* Otherwise an actively fighting root is ready only after returning to
     * controllable idle standing. This mirrors System.stepRoundState():
     * ctrl && MoveType I && StateType S. */
    return fighter->ctrl &&
           fighter->cur_move_type == IK_CNS_MOVE_IDLE &&
           fighter->cur_state_type == IK_CNS_STATE_STAND;
}

static int round4_ready(const ik_fight_t* fight) {
    return fight &&
           fighter_ready_for_round4(&fight->fighters[0]) &&
           fighter_ready_for_round4(&fight->fighters[1]);
}

static void advance_outro_state(
    ik_fight_t* fight,
    int ready_at_frame_start
) {
    if (!fight || fight->round_state < 3u || fight->round_over) return;
    if (fight->round_outro_ticks < 0xffffu) ++fight->round_outro_ticks;

    /* Ikemen runs stepRoundState() before character states. Therefore the
     * readiness test for RoundState 4 sees the roots as they were at the
     * beginning of this frame, not a 5150/idle state they enter later during
     * the same tick. */
    if (fight->round_state == 3u &&
        fight->round_outro_ticks > IK_ROUND_OVER_WAIT_TIME) {
        if (!ready_at_frame_start) {
            fight->round_outro_ticks = IK_ROUND_OVER_WAIT_TIME;
            return;
        }

        fight->round_state = 4u;

        /* The first RoundState-4 frame clears control before character code
         * runs (System.stepRoundState in upstream). */
        fight->fighters[0].ctrl = 0;
        fight->fighters[1].ctrl = 0;
    }
}

static void start_post_round_poses(ik_fight_t* fight) {
    if (!fight || fight->round_state != 4u ||
        fight->round_outro_ticks <
            IK_ROUND_OVER_WAIT_TIME + IK_ROUND_OVER_WIN_TIME - 1u) {
        return;
    }

    /* Upstream performs these SelfStates in stepRoundState(), before the
     * character state pass. State 180 may immediately route to a character's
     * authored win pose (KFM: 180 -> 181) during this same tick. Defeated
     * roots are already SCF_over_ko there, so only living roots are forced. */
    for (int i = 0; i < 2; ++i) {
        const uint8_t bit = (uint8_t)(1u << i);
        if ((fight->win_pose_started_mask & bit) != 0u) continue;

        ik_fighter_t* f = &fight->fighters[i];
        if (f->hp <= 0) {
            fight->win_pose_started_mask |= bit;
            continue;
        }

        int16_t target = 175; /* draw */
        if (fight->winner != 0u) {
            target = fight->winner == (uint8_t)(i + 1) ? 180 : 170;
        }

        const ik_cns_asset_t* native_cns =
            cns_for_owner(fight, f->owner_player);
        if (ik_cns_find_state(native_cns, target)) {
            f->state_owner = f->owner_player;
            ikf_enter_state(fight, f, target);
        }
        fight->win_pose_started_mask |= bit;
    }
}

static int run_priority(const ik_fighter_t* f) {
    if (f->cur_move_type == IK_CNS_MOVE_ATTACK) return 5;
    return f->cur_move_type == IK_CNS_MOVE_IDLE ? 4 : 3;
}

void ik_fight_update(ik_fight_t* fight,
                     const ik_fight_controls_t* p1,
                     const ik_fight_controls_t* p2,
                     const ik_frame_table_t* p1_frames,
                     const ik_frame_table_t* p2_frames) {
    if (!fight || !p1_frames) return;
    if (!p2_frames) p2_frames = p1_frames;
    const ik_frame_inputs_t in = {{p1, p2}, {p1_frames, p2_frames}};

    begin_frame(fight, &in);
    if (fight->round_over) {
        update_round_over(fight, p1);
        return;
    }
    if (fight->pause_time > 0u) {
        update_paused(fight, &in);
        return;
    }

    fight->frame++;

    /* Win/lose/draw SelfStates are also part of upstream stepRoundState(), so
     * they must be installed before the fighters execute this frame. */
    start_post_round_poses(fight);

    /* stepRoundState() runs before character state execution upstream.
     * Snapshot readiness now and use it only if this rendered frame advances
     * the KO outro counter below. */
    const int round4_ready_at_frame_start = round4_ready(fight);

    /* Upstream exposes the lethal hit with RoundState still at 2 for the
     * deciding frame. The KO transition becomes visible on the next logical
     * tick, after life has already reached zero. That transition tick itself
     * still executes normally; KO slow motion starts throttling subsequent
     * ticks. This matters for hit-pause/state clocks on the first KO frame. */
    const uint8_t round_state_before_ko = fight->round_state;
    check_knockout(fight, &in);
    const int ko_started_this_tick =
        round_state_before_ko < 3u && fight->round_state >= 3u;

    ik_ko_phase_t ko_phase = {1u, 1u};
    int split_ko_clocks = 0;
    if (!ko_started_this_tick &&
        fight->round_state >= 3u && fight->ko_slow_ticks > 0u) {
        ko_phase = ko_phase_advance(fight);
        split_ko_clocks = 1;
        /* Contact gathering must use the HitDef already activated by the last
         * tickFrame. In particular, a tickNextFrame that merely advances into
         * a trigger element must not execute that HitDef controller itself. */
        fight->ko_split_clocks = 1u;

        /* tickNextFrame can occur on a rendered frame with no tickFrame.
         * Animation/HitPause advance first; collision then observes the new
         * animation frame. A hit created here must not have its fresh
         * HitPause decremented by this same tickNextFrame. */
        if (!ko_phase.tick_frame) {
            if (ko_phase.tick_next_frame) {
                ikf_finish_slow_tick(fight);
                resolve_contacts(fight, &in);
                exit_targets(fight);
                ikf_update_guard_dist(fight);
            }
            fight->ko_split_clocks = 0u;
            return;
        }
    }

    tick_round_timer(fight);
    fight->ko_split_clocks = (uint8_t)split_ko_clocks;

    /* Upstream runs attackers first, then idle players, then the rest (a
     * fighter in a get-hit state); equal priority runs P1 first. */
    const int first = run_priority(&fight->fighters[1]) >
                              run_priority(&fight->fighters[0]) ? 1 : 0;
    for (int n = 0; n < 2; ++n) {
        const int i = first ^ n;
        ikf_step_fighter(
            fight, i, i == 0 ? p1 : p2, i == 1 && p2 == 0,
            i == 0 ? p1_frames : p2_frames, i == 0 ? p2_frames : p1_frames);
    }
    ikf_push_fighters(fight, p1_frames, p2_frames);
    advance_round_state(fight);
    step_entities(fight, &in, 0);
    if (split_ko_clocks) {
        /* State controllers execute on tickFrame, but KO-slow contacts are
         * deferred to tickNextFrame. This makes a newly authored HitDef active
         * (and clears HitDef targets) before it can actually connect. */
        refresh_root_hitdefs(fight, &in);
        ikf_camera_step(fight);
        if (ko_phase.tick_next_frame) {
            ikf_finish_slow_tick(fight);
            resolve_contacts(fight, &in);
        }
        exit_targets(fight);
    } else {
        resolve_contacts(fight, &in);
        exit_targets(fight);
        ikf_camera_step(fight);
        ikf_finish_tick(fight);
    }
    fight->ko_split_clocks = 0u;
    ikf_update_guard_dist(fight);
    if (fight->round_state >= 3u) {
        advance_outro_state(fight, round4_ready_at_frame_start);
    }
}
