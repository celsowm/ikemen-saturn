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
    const ik_frame_character_assets_t characters[2] = {
        {&p1_commands, nullptr}, {&p2_commands, nullptr}
    };

    static ik_frame_ctx_t ctx;
    ik_fight_t fight{};
    ik_fight_init(&fight, nullptr);
    OK(!ik_frame_ctx_init(&ctx, &fight, nullptr));
    OK(ik_frame_ctx_init(&ctx, &fight, characters));
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
    std::puts("[test] per-player CMD binding OK");
    return 0;
}
