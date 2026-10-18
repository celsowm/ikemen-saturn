#include <cstdio>
#include <cstdlib>
#include "ikemen_frame.h"
#include "ikemen_zss_ai.h"
#include "ikemen_saturn/kfm_zss_cns.h"
#include "ikemen_saturn/kfm_zss_frames.h"
#include "ikemen_saturn/kfm_zss_commands.h"

#define OK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); std::exit(1); } } while (0)

int main() {
    /* Exact golden Park-Miller vector for Go's pinned common.go Random().
     * The OC_random trigger is Rand(0,999), NOT raw %1000. */
    uint32_t golden_seed = 1u;
    const int32_t expected_next[] = {
        16807, 282475249, 1622650073, 984943658, 1144108930,
        470211272, 101027544, 1457850878, 1458777923, 2007237709
    };
    const int32_t expected_trigger[] = {
        0, 131, 755, 458, 532, 218, 47, 678, 679, 934
    };
    OK(ik_zss_ai_rng_next(nullptr) == 0);
    OK(ik_zss_ai_random_trigger(nullptr) == 0);
    for (unsigned i = 0; i < 10u; ++i) {
        const int32_t value = ik_zss_ai_rng_next(&golden_seed);
        OK(value == expected_next[i] && golden_seed == (uint32_t)value);
    }
    golden_seed = 1u;
    for (unsigned i = 0; i < 10u; ++i) {
        OK(ik_zss_ai_random_trigger(&golden_seed) ==
           expected_trigger[i]);
    }
    OK(golden_seed == 2007237709u);
    uint32_t zero_seed = 0u;
    OK(ik_zss_ai_rng_next(&zero_seed) == 2147483646);
    uint32_t max_seed = UINT32_C(2147483647);
    OK(ik_zss_ai_rng_next(&max_seed) == 2147483646);
    uint32_t neg_seed = UINT32_C(0xFFFFFFFF);
    OK(ik_zss_ai_rng_next(&neg_seed) == 2147466840);
    uint32_t independent_a = 1u, independent_b = 1u;
    OK(ik_zss_ai_rng_next(&independent_a) == 16807);
    OK(independent_b == 1u);
    OK(ik_zss_ai_rng_next(&independent_b) == 16807);

    ik_fight_t fight{};
    fight.round_state = 2;
    ik_fighter_t* f = &fight.fighters[1];
    int16_t next = 77;
    OK(!ik_zss_ai_request(nullptr, 1, 8, &next));
    OK(!ik_zss_ai_request(&fight, 2, 8, &next));
    OK(!ik_zss_ai_request(&fight, 1, 0, &next));
    OK(!ik_zss_ai_request(&fight, 1, 9, &next));
    OK(!ik_zss_ai_request(&fight, 1, 8, nullptr));
    OK(next == 77);

    f->state = 1061;
    f->vy_q8 = -257;
    f->move_hit = 1;
    OK(ik_zss_ai_request(&fight, 1, 8, &next) && next == 1055);
    f->state = 1051;
    OK(ik_zss_ai_request(&fight, 1, 1, &next) && next == 1055);
    f->state = 1071;
    OK(ik_zss_ai_request(&fight, 1, 8, &next) && next == 1075);
    f->vy_q8 = -256;
    next = 77;
    OK(!ik_zss_ai_request(&fight, 1, 8, &next) && next == 77);
    f->vy_q8 = -512;
    f->move_hit = 0;
    f->move_contact = 1;
    OK(!ik_zss_ai_request(&fight, 1, 6, &next));
    OK(ik_zss_ai_request(&fight, 1, 5, &next) && next == 1075);
    f->move_contact = 0;
    OK(!ik_zss_ai_request(&fight, 1, 5, &next));
    f->move_hit = 1;
    fight.round_state = 3;
    OK(!ik_zss_ai_request(&fight, 1, 8, &next));

    /* State -1 gurt is persistent, while AIJ and AI_JI are per-frame.
     * This fixture tests state bookkeeping separately from move ordering. */
    ik_zss_ai_memory_t mem{};
    ik_fight_t memory_fight{};
    memory_fight.round_state = 3u;
    ik_fighter_t* mf = &memory_fight.fighters[1];
    ik_fighter_t* mo = &memory_fight.fighters[0];
    mf->ctrl = 1;
    mf->anim = 0;
    mo->hitstun = 12u;
    mo->ctrl = 0;
    ik_zss_ai_memory_step(&memory_fight, 1, &mem);
    OK(mem.gurt == 10u && mem.ai_ji == 0u && mem.aij == 0u);
    memory_fight.round_state = 2u;
    mf->anim = 5120;
    ik_zss_ai_memory_step(&memory_fight, 1, &mem);
    OK(mem.gurt == 9u && mem.ai_ji == 12u);
    mf->anim = 0;
    for (int i = 0; i < 9; ++i) {
        ik_zss_ai_memory_step(&memory_fight, 1, &mem);
    }
    OK(mem.gurt == 0u && mem.ai_ji == 12u);
    mo->ctrl = 1;
    ik_zss_ai_memory_step(&memory_fight, 1, &mem);
    OK(mem.ai_ji == 0u && mem.gurt == 0u);
    mem.aij = 1u;
    ik_zss_ai_memory_step(&memory_fight, 1, &mem);
    OK(mem.aij == 0u); /* no persisted jump decision */
    ik_zss_ai_memory_step(nullptr, 1, &mem);
    ik_zss_ai_memory_step(&memory_fight, 2, &mem);
    ik_zss_ai_memory_step(&memory_fight, 1, nullptr);
    OK(mem.gurt == 0u && mem.aij == 0u);

    /* The local AI_JI opportunity suppresses *neutral* light/medium
     * choices while the opponent has remaining hitstun. Clearing the
     * opportunity must immediately restore the ordinary jab branch. */
    ik_zss_ai_memory_t chase_memory{};
    ik_fight_t chase_fight{};
    chase_fight.round_state = 2u;
    ik_fighter_t* hunter = &chase_fight.fighters[1];
    ik_fighter_t* target = &chase_fight.fighters[0];
    hunter->hp = target->hp = 1000;
    hunter->state = 0;
    hunter->facing = -1;
    hunter->x = 150;
    hunter->on_ground = hunter->ctrl = 1;
    hunter->cur_state_type = IK_CNS_STATE_STAND;
    hunter->cur_move_type = IK_CNS_MOVE_IDLE;
    target->x = 110; /* facing-relative body distance 40 */
    target->cur_state_type = IK_CNS_STATE_STAND;
    target->cur_move_type = IK_CNS_MOVE_IDLE;
    target->hitstun = 12;
    target->ctrl = 0;
    uint32_t chase_seed = 1u;
    ik_fight_controls_t chase{};
    (void)ik_zss_ai_tick_memory(
        &chase_fight, 1u, 8u, &chase_seed, &chase_memory, &chase);
    OK(chase_memory.ai_ji == 12u);
    OK(!chase.has_state_request || chase.requested_state != 200);
    target->ctrl = 1;
    target->hitstun = 0;
    ik_fight_controls_t regained{};
    OK(ik_zss_ai_tick_memory(
        &chase_fight, 1u, 8u, &chase_seed, &chase_memory, &regained));
    OK(chase_memory.ai_ji == 0u);
    OK(regained.has_state_request && regained.requested_state == 200);

    static ik_frame_ctx_t ctx{};
    static ik_cns_asset_t cns{};
    static const ik_frame_table_t frames{};
    static const ik_cmd_name_t names[] = {{"x", 0, 0, 0}};
    ik_command_asset_t cmd{};
    cmd.names = names;
    cmd.name_count = 1u;
    const ik_frame_character_assets_t assets[2] = {
        {&cns, &frames, &cmd, nullptr}, {&cns, &frames, &cmd, nullptr}
    };
    OK(ik_frame_ctx_init(&ctx, &fight, assets));
    OK(ctx.zss_ai_level[0] == 0 && ctx.zss_ai_level[1] == 0);
    OK(ctx.zss_ai_memory[0].gurt == 0 &&
       ctx.zss_ai_memory[1].gurt == 0);
    OK(!ik_frame_set_zss_ai_level(&ctx, 2, 5));
    OK(!ik_frame_set_zss_ai_level(&ctx, 1, 9));
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 5));
    OK(ctx.zss_ai_level[0] == 0 && ctx.zss_ai_level[1] == 5);
    ctx.zss_ai_memory[1].gurt = 7u;
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 4)); /* keeps memory */
    OK(ctx.zss_ai_memory[1].gurt == 7u);
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 0));
    OK(ctx.zss_ai_level[1] == 0 && ctx.zss_ai_memory[1].gurt == 0);
    ctx.zss_ai_memory[1].gurt = 7u;
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 8)); /* reset on enable */
    OK(ctx.zss_ai_memory[1].gurt == 0u);
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 0));
    /* End-to-end: frame driver dispatches AI State -1 into real CNS/AIR.
     * P2 has no pad, but an opted-in CPU must no longer be an idle dummy.
     * This fixture enters native Strong Knee airborne State 1061 with a
     * registered MoveHit; the expected original branch requests 1055. */
    static ik_frame_ctx_t real_ctx{};
    static ik_fight_t real_fight{};
    static const ik_frame_table_t real_frames = {
        kfm_zss_frames, KFM_ZSS_FRAME_COUNT,
        kfm_zss_clsn_boxes, KFM_ZSS_CLSN_BOX_COUNT
    };
    const ik_frame_character_assets_t zss[2] = {
        {&kfm_zss_cns, &real_frames, &kfm_zss_commands, nullptr},
        {&kfm_zss_cns, &real_frames, &kfm_zss_commands, nullptr}
    };
    OK(ik_frame_ctx_init(&real_ctx, &real_fight, zss));
    OK(ik_frame_set_zss_ai_level(&real_ctx, 1, 8));
    real_fight.round_state = 2u;
    ik_fighter_t* cpu = &real_fight.fighters[1];
    cpu->state = 1061;
    cpu->state_time = 3u;
    cpu->statedef_pending = 0u;
    cpu->cur_state_type = IK_CNS_STATE_AIR;
    cpu->cur_move_type = IK_CNS_MOVE_ATTACK;
    cpu->on_ground = 0u;
    cpu->ctrl = 0;
    cpu->anim = 1051;
    cpu->anim_time = 2u;
    cpu->y_q8 = (IK_FLOOR_Y - 45) * IK_CNS_Q8_ONE;
    cpu->y = IK_FLOOR_Y - 45;
    cpu->vy_q8 = -4 * IK_CNS_Q8_ONE;
    cpu->move_hit = 1u;
    sat_pad_state_t neutral{};
    neutral.connected = 1u;
    ik_frame_step(&real_ctx, &real_fight, &neutral, nullptr);
    OK(cpu->state == 1055);
    OK(real_ctx.zss_ai_level[0] == 0u);

    ik_fight_t neutral_fight{};
    neutral_fight.round_state = 2u;
    ik_fighter_t* attacker = &neutral_fight.fighters[1];
    ik_fighter_t* victim = &neutral_fight.fighters[0];
    attacker->hp = victim->hp = 1000;
    attacker->facing = -1;
    attacker->on_ground = attacker->ctrl = 1;
    attacker->cur_state_type = IK_CNS_STATE_STAND;
    attacker->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->state = 0;
    attacker->x = 240;
    victim->x = 30;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    uint32_t random_a = 1u, random_b = 1u;
    int saw_run = 0;
    for (int frame = 0; frame < 24; ++frame) {
        ik_fight_controls_t a{}, b{};
        int ra = ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &a);
        int rb = ik_zss_ai_tick(&neutral_fight, 1, 8, &random_b, &b);
        OK(ra == rb && a.has_state_request == b.has_state_request);
        OK(a.requested_state == b.requested_state);
        if (a.has_state_request && a.requested_state == 100) saw_run = 1;
    }
    OK(saw_run && random_a == random_b);
    uint32_t before = random_a;
    ik_fight_controls_t disabled{};
    OK(!ik_zss_ai_tick(&neutral_fight, 1, 0, &random_a, &disabled));
    OK(random_a == before);

    /* GO AI.zss close throw: source-guarded <=310*level^2/48.
     * With seed 1 the first Rand(0,999)=0. This must enter the actual
     * throw state 800 and advance the pinned Park-Miller stream once. */
    attacker->state = 0;
    attacker->x = 140;
    victim->x = 125;
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    attacker->move_contact = 0;
    uint32_t throw_seed = 1u;
    ik_fight_controls_t throw_start{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &throw_seed, &throw_start));
    OK(throw_start.has_state_request && throw_start.requested_state == 800);
    OK(throw_seed == 16807u);
    victim->cur_move_type = IK_CNS_MOVE_HIT;
    uint32_t blocked_throw_seed = 1u;
    ik_fight_controls_t blocked_throw{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8,
                         &blocked_throw_seed, &blocked_throw);
    OK(!blocked_throw.has_state_request || blocked_throw.requested_state != 800);
    OK(blocked_throw_seed == 1u);
    victim->cur_move_type = IK_CNS_MOVE_IDLE;

    /* Pinned AI.zss 186-242: an outer 55px light predicate does NOT
     * change the grounded inner <45px light gate. At 50px the original
     * executes a separate 250-scaled poke lottery, not the heavy 240
     * at <=425 gate (which has its own additional <45 condition). */
    attacker->x = 150;
    victim->x = 100;
    uint32_t medium_seed = 1u; /* rolls: 0, 131, 755 */
    ik_fight_controls_t stand_medium{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &medium_seed, &stand_medium));
    OK(stand_medium.has_state_request && stand_medium.requested_state == 440);
    OK(medium_seed == 1622650073u);
    victim->cur_state_type = IK_CNS_STATE_CROUCH;
    uint32_t crouch_seed = 1u;
    ik_fight_controls_t crouch_medium{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8,
                         &crouch_seed, &crouch_medium);
    OK(!crouch_medium.has_state_request ||
       (crouch_medium.requested_state != 200 &&
        crouch_medium.requested_state != 240 &&
        crouch_medium.requested_state != 440));
    /* No crouching fallback poke: native then evaluates the separate
     * walking probability, consuming one additional RNG value. */
    OK(crouch_seed == 984943658u);
    victim->cur_state_type = IK_CNS_STATE_STAND;

    /* Poke state selection is dependent on INDEPENDENT random draws,
     * and the conditional third draw occurs only in the 45..50px zone. */
    uint32_t poke210_seed = 7u; /* 0, 920; 920%4 == 0 */
    ik_fight_controls_t poke210{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &poke210_seed, &poke210));
    OK(poke210.has_state_request && poke210.requested_state == 210);
    OK(poke210_seed == 1977326743u);
    uint32_t poke240_seed = 6u; /* 0, 789, 533; 533%4 == 1 */
    ik_fight_controls_t poke240{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &poke240_seed, &poke240));
    OK(poke240.has_state_request && poke240.requested_state == 240);
    OK(poke240_seed == 1145965850u);
    victim->x = 95; /* 55px: third random must NOT be evaluated */
    uint32_t far_poke_seed = 1u;
    ik_fight_controls_t far_poke{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &far_poke_seed, &far_poke));
    OK(far_poke.has_state_request && far_poke.requested_state == 440);
    OK(far_poke_seed == 282475249u);
    victim->x = 89; /* 61px: no poke draw and no move */
    uint32_t out_of_poke_seed = 1u;
    ik_fight_controls_t no_poke{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8,
                         &out_of_poke_seed, &no_poke);
    OK(!no_poke.has_state_request || 
       (no_poke.requested_state != 210 &&
        no_poke.requested_state != 240 &&
        no_poke.requested_state != 440));

    /* AI.zss State -1 jump decision around lines 498-523.
     * Opponent attacking at 85px and AI level 8 permits jump even if
     * the random branch failed. It MUST still consume that RNG draw. */
    attacker->state = 0;
    attacker->prev_state = 0;
    attacker->ctrl = attacker->on_ground = 1;
    attacker->cur_state_type = IK_CNS_STATE_STAND;
    attacker->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->x = 140;
    victim->x = 55;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    victim->cur_move_type = IK_CNS_MOVE_ATTACK;
    uint32_t jump_seed = 282475249u; /* next roll=755; gate 500 fails */
    ik_fight_controls_t threat_jump{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &jump_seed, &threat_jump));
    OK(threat_jump.has_state_request && threat_jump.requested_state == 40);
    OK(threat_jump.forward && jump_seed == 1622650073u);
    /* The integrated CPU remembers gurt even if the present frame has
     * otherwise valid jump conditions. Later frames can resume jumping. */
    ik_zss_ai_memory_t jump_mem{};
    jump_mem.gurt = 10u;
    uint32_t locked_seed = 282475249u;
    ik_fight_controls_t blocked_getup{};
    (void)ik_zss_ai_tick_memory(
        &neutral_fight, 1, 8, &locked_seed, &jump_mem, &blocked_getup);
    OK(jump_mem.gurt == 9u && !jump_mem.aij);
    OK(!blocked_getup.has_state_request ||
       blocked_getup.requested_state != 40);
    for (int i = 0; i < 9; ++i) {
        ik_zss_ai_memory_step(&neutral_fight, 1, &jump_mem);
    }
    OK(jump_mem.gurt == 0u);
    uint32_t resume_seed = 1u;
    ik_fight_controls_t resumed_jump{};
    OK(ik_zss_ai_tick_memory(
        &neutral_fight, 1, 8, &resume_seed, &jump_mem, &resumed_jump));
    OK(resumed_jump.has_state_request &&
       resumed_jump.requested_state == 40 && jump_mem.aij == 1u);
    OK(resume_seed == 16807u);
    /* Original State -1 also permits jump from walking State 20 when Ctrl
     * is disabled; the native dispatcher must not drop that decision. */
    attacker->state = 20;
    attacker->ctrl = 0;
    uint32_t walking_jump_seed = 1u;
    ik_fight_controls_t walking_jump{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &walking_jump_seed, &walking_jump));
    OK(walking_jump.has_state_request && walking_jump.requested_state == 40);
    OK(walking_jump_seed == 16807u);
    attacker->state = 0;
    attacker->ctrl = 1;
    /* Below level 7 that alternative is forbidden when away from edges. */
    uint32_t low_level_seed = 1u;
    ik_fight_controls_t low_level_jump{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 6,
                       &low_level_seed, &low_level_jump);
    OK(!low_level_jump.has_state_request ||
       low_level_jump.requested_state != 40);
    /* The old walking fallback may still draw its own RNG and choose
     * State 20: lack of jump is the contract, not global RNG silence. */
    OK(low_level_seed == 16807u);
    /* Edge-driven jump is random gated and uses the source's strict <.
     * A 755 roll rejects it, while seed 1 produces zero and requests 40. */
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->x_q8 = 140 * IK_CNS_Q8_ONE;
    attacker->xmin_q8 = 120 * IK_CNS_Q8_ONE;
    attacker->xmax_q8 = 305 * IK_CNS_Q8_ONE;
    uint32_t edge_seed = 1u;
    ik_fight_controls_t edge_jump{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &edge_seed, &edge_jump));
    OK(edge_jump.has_state_request && edge_jump.requested_state == 40);
    OK(edge_seed == 16807u);
    uint32_t rejected_seed = 282475249u;
    ik_fight_controls_t rejected_jump{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &rejected_seed,
                        &rejected_jump);
    OK(!rejected_jump.has_state_request ||
       rejected_jump.requested_state != 40);
    /* Jump rejection consumes the first draw; the existing walk
     * fallback then evaluates its own random gate. */
    OK(rejected_seed == 984943658u);
    /* The original jump cancel expression disallows close neutral
     * attempts; at 60px the new branch must not steal an attack. */
    victim->x = 80;
    uint32_t near_seed = 1u;
    ik_fight_controls_t near_jump{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &near_seed, &near_jump);
    OK(!near_jump.has_state_request || near_jump.requested_state != 40);
    /* Restore legacy uninitialized bounds used by earlier fixtures. */
    attacker->x_q8 = attacker->xmin_q8 = attacker->xmax_q8 = 0;

    attacker->state = 100;
    attacker->x = 110;
    victim->x = 90;
    ik_fight_controls_t stop{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &stop));
    OK(stop.has_state_request && stop.requested_state == 0);
    attacker->state = 0;
    attacker->x = 140;
    victim->x = 100;
    ik_fight_controls_t jab{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &jab));
    OK(jab.has_state_request && jab.requested_state == 200);
    victim->cur_state_type = IK_CNS_STATE_CROUCH;
    ik_fight_controls_t crouch{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &crouch));
    OK(crouch.has_state_request && crouch.requested_state == 400);

    /* CPU needs to attack from State 20 before applying AIw walk direction;
     * otherwise a 30px spacing preference prevents combat indefinitely. */
    attacker->state = 20;
    attacker->ctrl = 1;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->x = 150;
    victim->x = 120;
    int walk_attack = 0;
    for (int i = 0; i < 80; ++i) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 200)
            walk_attack = 1;
    }
    OK(walk_attack);
    /* Source-informed CPU defense: verify both parry and held-back guard
     * without changing the human P1 command stream. */
    attacker->state = 0;
    attacker->ctrl = attacker->on_ground = 1;
    attacker->cur_state_type = IK_CNS_STATE_STAND;
    attacker->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->x = 140;
    victim->x = 120;
    attacker->y = victim->y = 180;
    attacker->in_guard_dist = 1;
    victim->cur_move_type = IK_CNS_MOVE_ATTACK;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    victim->state_time = 4;
    int saw_parry = 0, saw_guard = 0;
    for (int n = 0; n < 80; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 1300) saw_parry = 1;
        if (c.back && !c.has_state_request) saw_guard = 1;
    }
    OK(saw_parry && saw_guard);

    /* AI anti-air Upper: opponent movement and power select the variants. */
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    victim->cur_state_type = IK_CNS_STATE_AIR;
    victim->y = 120;
    attacker->in_guard_dist = 0;
    attacker->power = 0;
    victim->vx_q8 = -IK_CNS_Q8_ONE;
    victim->facing = 1;
    int saw_weak_upper = 0, saw_strong_upper = 0, saw_fast_upper = 0;
    for (int n = 0; n < 80; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 1100)
            saw_weak_upper = 1;
    }
    victim->vx_q8 = IK_CNS_Q8_ONE;
    for (int n = 0; n < 80; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 1110)
            saw_strong_upper = 1;
    }
    attacker->power = 600;
    for (int n = 0; n < 80; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 1120)
            saw_fast_upper = 1;
    }
    OK(saw_weak_upper && saw_strong_upper && saw_fast_upper);

    /* Go AI.zss anti-air normal (line 156): an unsuccessful Upper roll
     * is followed by its own inclusive 420-scaled random draw.
     * Seed 282475249 -> 755 (Upper fails), then 458 (normal succeeds). */
    attacker->state = 0;
    attacker->ctrl = attacker->on_ground = 1;
    attacker->cur_state_type = IK_CNS_STATE_STAND;
    attacker->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->x = 140;
    attacker->y = 180;
    victim->x = 110;
    victim->y = 135;
    victim->state = 0;
    victim->cur_state_type = IK_CNS_STATE_AIR;
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    attacker->power = 0;
    uint32_t anti_normal_seed = 282475249u;
    ik_fight_controls_t anti_normal{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &anti_normal_seed,
                      &anti_normal));
    OK(anti_normal.has_state_request && anti_normal.requested_state == 410);
    OK(anti_normal_seed == 984943658u);
    victim->state = 5040;
    uint32_t no_juggle_seed = 282475249u;
    ik_fight_controls_t no_juggle{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &no_juggle_seed, &no_juggle);
    OK(!no_juggle.has_state_request || no_juggle.requested_state != 410);

    /* AI.zss line 540: when a foe attacks from close range, use the
     * original 296 chance to enter the existing backdash CNS State 105.
     * Avoid the earlier Upper/normal path using the opponent's height. */
    victim->state = 0;
    victim->cur_move_type = IK_CNS_MOVE_ATTACK;
    victim->state_time = 0; /* parry/guard block requires >1 */
    victim->y = 80;
    victim->x = 115; /* 25px in front */
    attacker->x_q8 = 140 * IK_CNS_Q8_ONE;
    attacker->xmin_q8 = 15 * IK_CNS_Q8_ONE;
    attacker->xmax_q8 = 305 * IK_CNS_Q8_ONE;
    uint32_t dash_seed = 1u;
    ik_fight_controls_t dash{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &dash_seed, &dash));
    OK(dash.has_state_request && dash.requested_state == 105);
    OK(dash_seed == 16807u);
    uint32_t dash_rejected_seed = 282475249u;
    ik_fight_controls_t dash_rejected{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &dash_rejected_seed,
                         &dash_rejected);
    OK(!dash_rejected.has_state_request ||
       dash_rejected.requested_state != 105);
    OK(dash_rejected_seed == 1622650073u);
    attacker->xmax_q8 = 170 * IK_CNS_Q8_ONE; /* 30px back: no dash */
    uint32_t dash_no_space_seed = 1u;
    ik_fight_controls_t dash_no_space{};
    (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &dash_no_space_seed,
                         &dash_no_space);
    OK(!dash_no_space.has_state_request ||
       dash_no_space.requested_state != 105);
    attacker->x_q8 = attacker->xmin_q8 = attacker->xmax_q8 = 0;
    victim->y = 180;
    victim->cur_move_type = IK_CNS_MOVE_IDLE;
    victim->cur_state_type = IK_CNS_STATE_STAND;

    /* CPU confirms a real contact AFTER hitpause, even with ctrl=0. */
    attacker->ctrl = 0;
    attacker->power = 0;
    attacker->state = 200;
    attacker->cur_move_type = IK_CNS_MOVE_ATTACK;
    attacker->move_hit = attacker->move_contact = 1;
    attacker->move_contact_time = 2;
    attacker->hit_pause = 0;
    victim->cur_move_type = IK_CNS_MOVE_HIT;
    victim->cur_state_type = IK_CNS_STATE_STAND;
    victim->hitstun = 14;
    victim->x = 110;  /* body distance 30 */
    int saw_chain = 0;
    for (int n = 0; n < 40; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 410) saw_chain = 1;
    }
    OK(saw_chain);
    attacker->state = 210;
    victim->x = 85;  /* distance 55: strong Palm cancel */
    ik_fight_controls_t palm{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &palm));
    OK(palm.has_state_request && palm.requested_state == 1010);
    attacker->move_contact_time = 4;  /* expired: no cancel */
    ik_fight_controls_t expired{};
    OK(!ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &expired));
    attacker->move_contact_time = 2;
    attacker->power = 1200;
    victim->hp = 200;
    victim->x = 120;
    int saw_finisher = 0;
    for (int n = 0; n < 40; ++n) {
        ik_fight_controls_t c{};
        (void)ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &c);
        if (c.has_state_request && c.requested_state == 3050)
            saw_finisher = 1;
    }
    OK(saw_finisher);

        neutral_fight.round_state = 3u;
    ik_fight_controls_t outro{};
    OK(!ik_zss_ai_tick(&neutral_fight, 1, 8, &random_a, &outro));

    /* Real frame driver with generated CNS/AIR: unplugged CPU attacks. */
    static ik_frame_ctx_t cpu_ctx{};
    static ik_fight_t cpu_fight{};
    OK(ik_frame_ctx_init(&cpu_ctx, &cpu_fight, zss));
    OK(ik_frame_set_zss_ai_level(&cpu_ctx, 1, 8));
    cpu_fight.round_state = 2u;
    cpu_fight.fighters[0].x = 120;
    cpu_fight.fighters[0].x_q8 = 120 * IK_CNS_Q8_ONE;
    cpu_fight.fighters[1].x = 170;
    cpu_fight.fighters[1].x_q8 = 170 * IK_CNS_Q8_ONE;
    cpu_fight.fighters[0].facing = 1;
    cpu_fight.fighters[1].facing = -1;
    int saw_attack = 0;
    for (int frame = 0; frame < 150; ++frame) {
        ik_frame_step(&cpu_ctx, &cpu_fight, &neutral, nullptr);
        if (cpu_fight.fighters[1].state == 200 ||
            cpu_fight.fighters[1].state == 400) saw_attack = 1;
    }
    OK(saw_attack);
    std::puts("[test] reproducible native CPU neutral decisions and attacks OK");
    std::puts("[test] source-checked opt-in native ZSS CPU knee cancel OK");
    return 0;
}
