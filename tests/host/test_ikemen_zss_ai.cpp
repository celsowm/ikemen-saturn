#include <cstdio>
#include <cstdlib>
#include "ikemen_frame.h"
#include "ikemen_zss_ai.h"
#include "ikemen_saturn/kfm_zss_cns.h"
#include "ikemen_saturn/kfm_zss_frames.h"
#include "ikemen_saturn/kfm_zss_commands.h"

#define OK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); std::exit(1); } } while (0)

int main() {
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
    std::puts("[test] source-checked opt-in native ZSS CPU knee cancel OK");
    return 0;
}
