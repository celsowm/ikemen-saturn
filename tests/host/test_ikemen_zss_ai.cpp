#include <cstdio>
#include <cstdlib>
#include "ikemen_frame.h"
#include "ikemen_zss_ai.h"

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
    std::puts("[test] source-checked opt-in native ZSS CPU knee cancel OK");
    return 0;
}
