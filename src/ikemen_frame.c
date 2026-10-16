#include "ikemen_frame.h"

/* Resolve each player's commands once. Generated KFM IDs are not part of
 * the engine ABI; another character may number its CMD names differently. */
static const char* const k_control_names[IK_FRAME_CONTROL_COUNT] = {
    "holdfwd", "holdback", "holdup", "holddown",
    "a", "b", "c", "x", "y", "z", "start", "recovery"
};

typedef struct ik_rule_expr_user {
    ik_entity_expr_binding_t entity;
    const ik_command_state_t* command_state;
    const ik_command_asset_t* commands;
} ik_rule_expr_user_t;

static int rule_expr_read_field(
    void* user,
    uint8_t redirect,
    uint8_t field,
    int32_t index,
    int32_t redirect_id,
    uint8_t redirect_index,
    int32_t* out_value
) {
    if (!user) return 0;
    ik_rule_expr_user_t* rule = (ik_rule_expr_user_t*)user;
    return ik_entity_expr_read_field(
        &rule->entity, redirect, field, index,
        redirect_id, redirect_index, out_value);
}

static int rule_expr_read_command(
    void* user,
    uint16_t command_id,
    int32_t* out_value
) {
    if (!user || !out_value) return 0;
    const ik_rule_expr_user_t* rule =
        (const ik_rule_expr_user_t*)user;
    *out_value = ik_command_active(
        rule->command_state, rule->commands, command_id);
    return 1;
}

void ik_frame_sync_players(ik_frame_ctx_t* ctx, const ik_fight_t* fight) {
    if (!ctx || !fight) return;
    for (uint32_t i = 0u; i < 2u; ++i) {
        const ik_fighter_t* fighter = &fight->fighters[i];
        ik_entity_t* entity = ik_entity_get(&ctx->pool, ctx->players[i]);
        if (!entity) continue;

        const ik_cns_asset_t* state_cns =
            fighter->state_owner < 2u
                ? fight->player_cns[fighter->state_owner]
                : fight->cns;
        entity->x_q8 = fighter->x_q8;
        entity->y_q8 = fighter->y_q8;
        entity->vx_q8 = fighter->vx_q8;
        entity->vy_q8 = fighter->vy_q8;
        entity->state_no = fighter->state;
        entity->prev_state_no = fighter->prev_state;
        entity->state_time = fighter->state_time;
        entity->state_owner = fighter->state_owner;
        entity->anim_owner = fighter->anim_owner;
        entity->anim_no = fighter->anim;
        entity->anim_time = fighter->anim_time;
        entity->life = fighter->hp;
        entity->power = fighter->power;
        entity->active_hit_attr_mask = 0u;
        if (state_cns &&
            fighter->active_hitdef_global >= 0 &&
            fighter->active_hitdef_global < (int16_t)state_cns->hitdef_count) {
            entity->active_hit_attr_mask =
                state_cns->hitdefs[
                    (uint16_t)fighter->active_hitdef_global
                ].attack_attr_mask;
        }
        entity->push_back = fighter->push_back;
        entity->push_front = fighter->push_front;
        entity->facing = fighter->facing;
        entity->ctrl = (uint8_t)(fighter->ctrl != 0);
        entity->state_type = ik_fight_state_type(fight, fighter);
        entity->move_type = fighter->cur_move_type;
        entity->move_contact = fighter->move_contact;

        const int8_t target_index = fighter->target_index;
        const ik_entity_handle_t target =
            target_index >= 0 && target_index < 2
                ? ctx->players[(uint8_t)target_index]
                : ik_entity_invalid_handle();
        (void)ik_entity_set_target(&ctx->pool, ctx->players[i], target);
    }
}

int ik_frame_ctx_init(
    ik_frame_ctx_t* ctx, ik_fight_t* fight,
    const ik_frame_character_assets_t characters[2]
) {
    if (!ctx || !fight || !characters ||
        !characters[0].commands || !characters[1].commands) return 0;
    ik_entity_pool_init(&ctx->pool);
    if (!ik_entity_spawn(
            &ctx->pool, IK_ENTITY_PLAYER, 1, 0u,
            ik_entity_invalid_handle(), &ctx->players[0]) ||
        !ik_entity_spawn(
            &ctx->pool, IK_ENTITY_PLAYER, 2, 1u,
            ik_entity_invalid_handle(), &ctx->players[1])) {
        return 0;
    }
    ik_fight_bind_entities(
        fight, &ctx->pool, ctx->players[0], ctx->players[1]);
    ik_frame_sync_players(ctx, fight);
    for (uint32_t player = 0u; player < 2u; ++player) {
        ik_frame_character_t* character = &ctx->characters[player];
        character->commands = characters[player].commands;
        character->state_rules = characters[player].state_rules;
        for (uint32_t control = 0u; control < IK_FRAME_CONTROL_COUNT; ++control) {
            character->control_ids[control] = ik_command_find(
                character->commands, k_control_names[control]);
        }
        ik_command_state_init(&ctx->command_states[player]);
    }
    return 1;
}

static int command_pause_end_buffer(
    const ik_fight_t* fight,
    uint32_t player
) {
    if (!fight || player >= 2u || fight->pause_time == 0u ||
        fight->pause_end_cmd_buffer_time == 0u ||
        fight->pause_time > fight->pause_end_cmd_buffer_time) {
        return 0;
    }

    const int can_act =
        fight->pause_owner == (int8_t)player &&
        fight->pause_move_time > 0u;
    return !can_act;
}

static uint8_t control_active(
    const ik_frame_ctx_t* ctx, uint32_t player, ik_frame_control_t control
) {
    const ik_frame_character_t* character = &ctx->characters[player];
    return (uint8_t)ik_command_active(
        &ctx->command_states[player], character->commands,
        character->control_ids[control]);
}

static void controls_from_commands(
    const ik_frame_ctx_t* ctx, uint32_t player,
    ik_fight_controls_t* controls
) {
    if (!ctx || !controls || player >= 2u) return;
    const ik_fight_controls_t none = {0};
    *controls = none;
    const ik_frame_character_t* character = &ctx->characters[player];
    const ik_command_state_t* state = &ctx->command_states[player];

    controls->forward = control_active(ctx, player, IK_FRAME_CONTROL_HOLDFWD);
    controls->back = control_active(ctx, player, IK_FRAME_CONTROL_HOLDBACK);
    controls->up = control_active(ctx, player, IK_FRAME_CONTROL_HOLDUP);
    controls->down = control_active(ctx, player, IK_FRAME_CONTROL_HOLDDOWN);
    controls->a = control_active(ctx, player, IK_FRAME_CONTROL_A);
    controls->b = control_active(ctx, player, IK_FRAME_CONTROL_B);
    controls->c = control_active(ctx, player, IK_FRAME_CONTROL_C);
    controls->x = control_active(ctx, player, IK_FRAME_CONTROL_X);
    controls->y = control_active(ctx, player, IK_FRAME_CONTROL_Y);
    controls->z = control_active(ctx, player, IK_FRAME_CONTROL_Z);
    controls->start = control_active(ctx, player, IK_FRAME_CONTROL_START);
    controls->recovery = control_active(ctx, player, IK_FRAME_CONTROL_RECOVERY);

    ik_rule_expr_user_t user = {
        {&ctx->pool, ctx->players[player]}, state, character->commands
    };
    const ik_expr_context_t expression = {
        &user, rule_expr_read_field, rule_expr_read_command
    };
    int16_t requested = 0;
    if (character->state_rules && ik_command_eval_state_change_expr(
            character->state_rules, &expression, &requested)) {
        controls->requested_state = requested;
        controls->has_state_request = 1u;
    }
}

void ik_frame_step(
    ik_frame_ctx_t* ctx,
    ik_fight_t* fight,
    const sat_pad_state_t* pad1,
    const sat_pad_state_t* pad2,
    const ik_frame_table_t* frames_p1,
    const ik_frame_table_t* frames_p2
) {
    if (!ctx || !fight || !pad1) return;

    ik_fight_controls_t p1_controls = {0};
    ik_fight_controls_t p2_controls = {0};

    ik_frame_sync_players(ctx, fight);
    ik_command_update(
        &ctx->command_states[0], ctx->characters[0].commands, pad1,
        fight->fighters[0].facing,
        fight->fighters[0].hit_pause != 0u,
        command_pause_end_buffer(fight, 0u));
    controls_from_commands(ctx, 0u, &p1_controls);

    if (pad2) {
        ik_command_update(
            &ctx->command_states[1], ctx->characters[1].commands, pad2,
            fight->fighters[1].facing,
            fight->fighters[1].hit_pause != 0u,
            command_pause_end_buffer(fight, 1u));
        controls_from_commands(ctx, 1u, &p2_controls);
    }

    ik_fight_update(
        fight, &p1_controls, pad2 ? &p2_controls : 0,
        frames_p1, frames_p2);
}
