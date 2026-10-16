#ifndef IKEMEN_FRAME_H
#define IKEMEN_FRAME_H

/* One simulation frame of the Ikemen fight, shared by the Saturn example and
 * by the host oracle tracer so both execute the exact same per-frame order:
 *
 *   sync players -> command update -> State -1 rules -> ik_fight_update
 *
 * Keeping this in one place is what makes an oracle diff a statement about
 * the console build rather than about a look-alike harness loop.
 */

#include <stdint.h>

#include "ikemen_anim.h"
#include "ikemen_command.h"
#include "ikemen_entity.h"
#include "ikemen_fight.h"
#include "saturn/input.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Bind canonical input controls by name instead of a character-specific ID. */
typedef enum ik_frame_control {
    IK_FRAME_CONTROL_HOLDFWD = 0, IK_FRAME_CONTROL_HOLDBACK,
    IK_FRAME_CONTROL_HOLDUP, IK_FRAME_CONTROL_HOLDDOWN,
    IK_FRAME_CONTROL_A, IK_FRAME_CONTROL_B, IK_FRAME_CONTROL_C,
    IK_FRAME_CONTROL_X, IK_FRAME_CONTROL_Y, IK_FRAME_CONTROL_Z,
    IK_FRAME_CONTROL_START, IK_FRAME_CONTROL_RECOVERY,
    IK_FRAME_CONTROL_COUNT
} ik_frame_control_t;

typedef struct ik_frame_character_assets {
    const ik_command_asset_t* commands;
    const ik_state_rule_asset_t* state_rules;
} ik_frame_character_assets_t;

typedef struct ik_frame_character {
    const ik_command_asset_t* commands;
    const ik_state_rule_asset_t* state_rules;
    uint16_t control_ids[IK_FRAME_CONTROL_COUNT];
} ik_frame_character_t;

typedef struct ik_frame_ctx {
    ik_frame_character_t characters[2];
    ik_command_state_t command_states[2];
    ik_entity_pool_t pool;
    ik_entity_handle_t players[2];
} ik_frame_ctx_t;

/* Spawns the two root players in the entity pool, binds them to the fight
 * and mirrors the initial fighter state into the pool. Returns 0 on pool
 * exhaustion or a missing CMD table. The caller retains ownership of the
 * character tables for the duration of the fight. */
int ik_frame_ctx_init(
    ik_frame_ctx_t* ctx, ik_fight_t* fight,
    const ik_frame_character_assets_t characters[2]);

/* Mirrors fighter state into the entity pool (what State -1 rules and
 * redirections read). Exposed because presentation code needs it before the
 * first step. */
void ik_frame_sync_players(ik_frame_ctx_t* ctx, const ik_fight_t* fight);

/* Advances one frame. pad2 == NULL means "no second pad": P2 is an idle
 * training dummy and its command buffer is left untouched. */
void ik_frame_step(
    ik_frame_ctx_t* ctx,
    ik_fight_t* fight,
    const sat_pad_state_t* pad1,
    const sat_pad_state_t* pad2,
    const ik_frame_table_t* frames_p1,
    const ik_frame_table_t* frames_p2);

#ifdef __cplusplus
}
#endif

#endif
