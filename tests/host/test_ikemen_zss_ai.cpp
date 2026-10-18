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
    OK(!ik_frame_set_zss_ai_level(&ctx, 2, 5));
    OK(!ik_frame_set_zss_ai_level(&ctx, 1, 9));
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 5));
    OK(ctx.zss_ai_level[0] == 0 && ctx.zss_ai_level[1] == 5);
    OK(ik_frame_set_zss_ai_level(&ctx, 1, 0));
    OK(ctx.zss_ai_level[1] == 0);
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

    /* At 50px, standing neutral extends the script's light reach to 55;
     * against a croucher, the preceding light subset does not reach and
     * the original medium-range heavy family can choose state 240. */
    attacker->x = 150;
    victim->x = 100;
    uint32_t medium_seed = 1u;
    ik_fight_controls_t stand_medium{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &medium_seed, &stand_medium));
    OK(stand_medium.has_state_request && stand_medium.requested_state == 200);
    OK(medium_seed == 1u);
    victim->cur_state_type = IK_CNS_STATE_CROUCH;
    ik_fight_controls_t crouch_medium{};
    OK(ik_zss_ai_tick(&neutral_fight, 1, 8,
                       &medium_seed, &crouch_medium));
    OK(crouch_medium.has_state_request &&
       crouch_medium.requested_state == 240);
    OK(medium_seed == 16807u);
    victim->cur_state_type = IK_CNS_STATE_STAND;

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
