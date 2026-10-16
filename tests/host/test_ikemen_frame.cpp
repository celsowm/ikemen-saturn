#include <cstdio>
#include <cstdlib>
#include "ikemen_frame.h"

#define OK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); std::exit(1); } } while (0)

/* The two command assets deliberately assign different numeric IDs to
 * identical names; no KFM enum can be used by the generic frame driver. */
int main() {
    static const ik_cmd_name_t p1_names[] = {
        {"x", 0u, 0u, 0u}, {"holdfwd", 0u, 0u, 0u},
        {"recovery", 0u, 0u, 0u}
    };
    static const ik_cmd_name_t p2_names[] = {
        {"recovery", 0u, 0u, 0u}, {"holdfwd", 0u, 0u, 0u},
        {"y", 0u, 0u, 0u}
    };
    ik_command_asset_t p1_commands{};
    p1_commands.names = p1_names;
    p1_commands.name_count = 3u;
    ik_command_asset_t p2_commands{};
    p2_commands.names = p2_names;
    p2_commands.name_count = 3u;
    /* Different CNS life constants prove independent state ownership.
     * Distinct AIR table addresses prove animations are bound separately. */
    static const ik_frame_table_t p1_frames{};
    static const ik_frame_table_t p2_frames{};
    static ik_cns_asset_t p1_cns{};
    static ik_cns_asset_t p2_cns{};
    p1_cns.constants.life = 950;
    p2_cns.constants.life = 1200;
    const ik_frame_character_assets_t characters[2] = {
        {&p1_cns, &p1_frames, &p1_commands, nullptr},
        {&p2_cns, &p2_frames, &p2_commands, nullptr}
    };

    static ik_frame_ctx_t ctx;
    ik_fight_t fight{};
    OK(!ik_frame_ctx_init(&ctx, &fight, nullptr));
    OK(ik_frame_ctx_init(&ctx, &fight, characters));
    OK(fight.player_cns[0] == &p1_cns);
    OK(fight.player_cns[1] == &p2_cns);
    OK(fight.player_frames[0] == &p1_frames);
    OK(fight.player_frames[1] == &p2_frames);
    OK(ctx.characters[0].cns == &p1_cns);
    OK(ctx.characters[1].cns == &p2_cns);
    OK(ctx.characters[0].frames == &p1_frames);
    OK(ctx.characters[1].frames == &p2_frames);
    OK(fight.fighters[0].hp == 950);
    OK(fight.fighters[1].hp == 1200);
    OK(ctx.characters[0].commands == &p1_commands);
    OK(ctx.characters[1].commands == &p2_commands);
    OK(ctx.characters[0].control_ids[IK_FRAME_CONTROL_X] == 0u);
    OK(ctx.characters[1].control_ids[IK_FRAME_CONTROL_X] == IK_CMD_INVALID_ID);
    OK(ctx.characters[0].control_ids[IK_FRAME_CONTROL_Y] == IK_CMD_INVALID_ID);
    OK(ctx.characters[1].control_ids[IK_FRAME_CONTROL_Y] == 2u);
    OK(ctx.characters[0].control_ids[IK_FRAME_CONTROL_HOLDFWD] == 1u);
    OK(ctx.characters[1].control_ids[IK_FRAME_CONTROL_HOLDFWD] == 1u);
    OK(ctx.characters[0].control_ids[IK_FRAME_CONTROL_RECOVERY] == 2u);
    OK(ctx.characters[1].control_ids[IK_FRAME_CONTROL_RECOVERY] == 0u);
    /* Round reset must preserve each fighter's CNS (and max life) too. */
    ik_fight_reset(&fight);
    OK(fight.player_cns[0] == &p1_cns);
    OK(fight.player_cns[1] == &p2_cns);
    OK(fight.player_frames[0] == &p1_frames);
    OK(fight.player_frames[1] == &p2_frames);
    OK(fight.fighters[0].hp == 950);
    OK(fight.fighters[1].hp == 1200);
    std::puts("[test] independent per-player CNS/AIR/CMD binding OK");
    return 0;
}
