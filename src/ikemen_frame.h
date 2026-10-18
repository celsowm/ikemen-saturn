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

/* All character-owned simulation data is supplied as a single bundle.
 * The frame driver owns no CNS/CMD/AIR payload; the caller retains it.
 * P1/P2 may use completely different generated bundles. */
typedef struct ik_frame_character_assets {
    const ik_cns_asset_t* cns;
    const ik_frame_table_t* frames;
    const ik_command_asset_t* commands;
    const ik_state_rule_asset_t* state_rules;
} ik_frame_character_assets_t;

typedef struct ik_frame_character {
    const ik_cns_asset_t* cns;
    const ik_frame_table_t* frames;
    const ik_command_asset_t* commands;
    const ik_state_rule_asset_t* state_rules;
    uint16_t control_ids[IK_FRAME_CONTROL_COUNT];
} ik_frame_character_t;

typedef struct ik_frame_ctx {
    ik_frame_character_t characters[2];
    ik_command_state_t command_states[2];
    ik_entity_pool_t pool;
    ik_entity_handle_t players[2];
    /* AI is off by default, independent for P1/P2. */
    uint8_t zss_ai_level[2];
    /* Independent reproducible local CPU random streams. */
    uint32_t zss_ai_rng[2];
} ik_frame_ctx_t;

/* Initializes a fight with independent CNS (including life, constants,
 * state and animation ownership), AIR and CMD/State -1 for each player.
 * Then binds player entities and mirrors the initial state. Returns 0 on
 * invalid bundles or entity-pool exhaustion. Caller owns every table. */
int ik_frame_ctx_init(
    ik_frame_ctx_t* ctx, ik_fight_t* fight,
    const ik_frame_character_assets_t characters[2]);

/* Mirrors fighter state into the entity pool (what State -1 rules and
 * redirections read). Exposed because presentation code needs it before the
 * first step. */
void ik_frame_sync_players(ik_frame_ctx_t* ctx, const ik_fight_t* fight);

/* Enable source-checked ZSS AI-only decisions for a character bound to
 * KFM ZSS. 0 restores human input, levels 1..8 enable limited CPU logic.
 * Also enables a seeded movement/grounded-light subset, not original RNG
 * or full ZSS AI parity. Returns 0 on error. */
int ik_frame_set_zss_ai_level(ik_frame_ctx_t* ctx,
                              uint8_t player, uint8_t level);

/* Advances one frame with the same character assets that were bound at
 * initialization. P2 without a pad is idle unless ZSS AI is enabled. */
void ik_frame_step(
    ik_frame_ctx_t* ctx,
    ik_fight_t* fight,
    const sat_pad_state_t* pad1,
    const sat_pad_state_t* pad2);

#ifdef __cplusplus
}
#endif

#endif
