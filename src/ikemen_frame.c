#include "ikemen_saturn/ikemen_frame.h"
#include "ikemen_saturn/ikemen_zss_ai.h"

/* Resolve each player's commands once. Generated KFM IDs are not part of
 * the engine ABI; another character may number its CMD names differently. */
static const char* const k_control_names[IK_FRAME_CONTROL_COUNT] = {
    "holdfwd", "holdback", "holdup", "holddown",
    "a", "b", "c", "x", "y", "z", "start", "recovery", "blocking"
};

typedef struct ik_rule_expr_user {
    ik_entity_expr_binding_t entity;
    const ik_command_state_t* command_state;
    const ik_command_asset_t* commands;
    const ik_fight_t* fight;
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
    /* State -1 belongs to the scene: its RoundState check cannot be
     * resolved from an individual entity's stored fields. */
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ROUND_STATE) {
        if (!rule->fight || !out_value) return 0;
        *out_value = rule->fight->round_state;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ANIM_ELEM_TIME) {
        if (!rule->fight || !out_value || index < 1 || index > 65535) return 0;
        const ik_entity_t* entity = ik_entity_get_const(
            rule->entity.pool, rule->entity.self);
        if (!entity) return 0;
        const uint8_t owner = entity->anim_owner;
        const ik_frame_table_t* frames =
            owner < 2u ? rule->fight->player_frames[owner] : 0;
        *out_value = ik_anim_elem_time(
            frames, entity->anim_no, entity->anim_time, (uint16_t)index);
        return 1;
    }
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
        entity->move_hit = fighter->move_hit;

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
    if (!ctx || !fight || !characters) return 0;
    for (uint32_t i = 0u; i < 2u; ++i) {
        if (!characters[i].cns || !characters[i].frames ||
            !characters[i].commands) return 0;
    }

    /* This is the only fight setup path: CNS and command sources can never
     * disagree because they are bound together before entities are spawned. */
    ik_fight_init_players(fight, characters[0].cns, characters[1].cns);
    fight->player_frames[0] = characters[0].frames;
    fight->player_frames[1] = characters[1].frames;
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
        character->cns = characters[player].cns;
        character->frames = characters[player].frames;
        character->commands = characters[player].commands;
        character->state_rules = characters[player].state_rules;
        for (uint32_t control = 0u; control < IK_FRAME_CONTROL_COUNT; ++control) {
            character->control_ids[control] = ik_command_find(
                character->commands, k_control_names[control]);
        }
        ik_command_state_init(&ctx->command_states[player]);
        ctx->zss_ai_level[player] = 0u;
        ctx->zss_ai_rng[player] = 1u + player;
        ctx->zss_ai_memory[player] = (ik_zss_ai_memory_t){0};
    }
    return 1;
}

int ik_frame_set_zss_ai_level(
    ik_frame_ctx_t* ctx, uint8_t player, uint8_t level
) {
    if (!ctx || player >= 2u || level > 8u ||
        !ctx->characters[player].cns || !ctx->characters[player].frames)
        return 0;
    /* Disabling or freshly enabling AI must not inherit an old match's
     * gurt window or transient declarations. Level adjustments retain it. */
    if (level == 0u || ctx->zss_ai_level[player] == 0u) {
        ctx->zss_ai_memory[player] = (ik_zss_ai_memory_t){0};
    }
    ctx->zss_ai_level[player] = level;
    return 1;
}

/* AI players don't produce pads; give the shared command tracker the same
 * view so common CNS states can poll command = "holdfwd"/"holdback"/...
 * while the CPU is driving. Held bits only - input_update derives the rest. */
static void ai_command_pad(const ik_fight_controls_t* controls, int facing,
                           sat_pad_state_t* out) {
    uint16_t held = 0u;
    const int fwd_right = facing >= 0;
    if (controls->forward) held |= fwd_right ? SAT_PAD_RIGHT : SAT_PAD_LEFT;
    if (controls->back)    held |= fwd_right ? SAT_PAD_LEFT  : SAT_PAD_RIGHT;
    if (controls->up)      held |= SAT_PAD_UP;
    if (controls->down)    held |= SAT_PAD_DOWN;
    if (controls->a)       held |= SAT_PAD_A;
    if (controls->b)       held |= SAT_PAD_B;
    if (controls->c)       held |= SAT_PAD_C;
    if (controls->x)       held |= SAT_PAD_X;
    if (controls->y)       held |= SAT_PAD_Y;
    if (controls->z)       held |= SAT_PAD_Z;
    if (controls->start)   held |= SAT_PAD_START;
    *out = (sat_pad_state_t){ held, held, 0u, 1u, 0u };
}

/* Scripted CPU logic is intentionally distinct from human CMD evaluation. */
static void ai_controls(
    ik_frame_ctx_t* ctx, const ik_fight_t* fight, uint8_t player,
    ik_fight_controls_t* out
) {
    (void)ik_zss_ai_tick_memory(
        fight, player, ctx->zss_ai_level[player],
        &ctx->zss_ai_rng[player], &ctx->zss_ai_memory[player], out);
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

static void sync_expression_commands(
    ik_frame_ctx_t* ctx, ik_fight_t* fight, uint32_t player
) {
    if (!ctx || !fight || player >= 2u) return;
    ik_fighter_t* fighter = &fight->fighters[player];
    fighter->command_active[0] = 0u;
    fighter->command_active[1] = 0u;
    const ik_command_asset_t* commands = ctx->characters[player].commands;
    for (uint16_t id = 0u; commands && id < commands->name_count && id < 128u; ++id) {
        if (ik_command_active(&ctx->command_states[player], commands, id)) {
            fighter->command_active[id / 64u] |= UINT64_C(1) << (id % 64u);
        }
    }
}

static void controls_from_commands(
    const ik_frame_ctx_t* ctx, const ik_fight_t* fight, uint32_t player,
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
    controls->blocking = control_active(ctx, player, IK_FRAME_CONTROL_BLOCKING);

    ik_rule_expr_user_t user = {
        {&ctx->pool, ctx->players[player]}, state, character->commands, fight
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
    const sat_pad_state_t* pad2
) {
    if (!ctx || !fight || !pad1) return;

    ik_fight_controls_t p1_controls = {0};
    ik_fight_controls_t p2_controls = {0};

    ik_frame_sync_players(ctx, fight);
    if (ctx->zss_ai_level[0] != 0u) {
        ai_controls(ctx, fight, 0u, &p1_controls);
        sat_pad_state_t ai_pad;
        ai_command_pad(&p1_controls, fight->fighters[0].facing, &ai_pad);
        ik_command_update(
            &ctx->command_states[0], ctx->characters[0].commands, &ai_pad,
            fight->fighters[0].facing,
            fight->fighters[0].hit_pause != 0u,
            command_pause_end_buffer(fight, 0u));
        sync_expression_commands(ctx, fight, 0u);
    } else {
        ik_command_update(
            &ctx->command_states[0], ctx->characters[0].commands, pad1,
            fight->fighters[0].facing,
            fight->fighters[0].hit_pause != 0u,
            command_pause_end_buffer(fight, 0u));
        sync_expression_commands(ctx, fight, 0u);
        controls_from_commands(ctx, fight, 0u, &p1_controls);
    }

    if (ctx->zss_ai_level[1] != 0u) {
        ai_controls(ctx, fight, 1u, &p2_controls);
        sat_pad_state_t ai_pad;
        ai_command_pad(&p2_controls, fight->fighters[1].facing, &ai_pad);
        ik_command_update(
            &ctx->command_states[1], ctx->characters[1].commands, &ai_pad,
            fight->fighters[1].facing,
            fight->fighters[1].hit_pause != 0u,
            command_pause_end_buffer(fight, 1u));
        sync_expression_commands(ctx, fight, 1u);
    } else if (pad2) {
        ik_command_update(
            &ctx->command_states[1], ctx->characters[1].commands, pad2,
            fight->fighters[1].facing,
            fight->fighters[1].hit_pause != 0u,
            command_pause_end_buffer(fight, 1u));
        sync_expression_commands(ctx, fight, 1u);
        controls_from_commands(ctx, fight, 1u, &p2_controls);
    }

    ik_fight_update(
        fight, &p1_controls, (pad2 || ctx->zss_ai_level[1]) ? &p2_controls : 0,
        ctx->characters[0].frames, ctx->characters[1].frames);
}
