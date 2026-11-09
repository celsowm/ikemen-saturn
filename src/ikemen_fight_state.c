/* State transitions: ChangeState bookkeeping and controlled input. */
#include "ikemen_fight_internal.h"

typedef struct ikf_expr_binding {
    const ik_fight_t* fight;
    const ik_fighter_t* fighter;
    ik_entity_expr_binding_t entity;
} ikf_expr_binding_t;

static int ikf_expr_read_field(
    void* user, uint8_t redirect, uint8_t field,
    int32_t index, int32_t redirect_id, uint8_t redirect_index,
    int32_t* out_value
) {
    if (!user || !out_value) return 0;
    const ikf_expr_binding_t* binding = (const ikf_expr_binding_t*)user;
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_GAME_TIME) {
        *out_value = (int32_t)binding->fight->frame;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_RANDOM) {
        const ik_fighter_t* f = binding->fighter;
        uint32_t value = binding->fight->frame * 0x9e3779b9u;
        if (f) {
            value ^= (uint32_t)(uint16_t)f->state * 0x85ebca6bu;
            value ^= (uint32_t)f->state_time * 0xc2b2ae35u;
            value ^= (uint32_t)f->owner_player * 0x27d4eb2fu;
        } else {
            const ik_entity_t* e = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (e) {
                value ^= (uint32_t)(uint16_t)e->state_no * 0x85ebca6bu;
                value ^= (uint32_t)e->state_time * 0xc2b2ae35u;
                value ^= (uint32_t)e->id * 0x27d4eb2fu;
            }
        }
        value ^= value >> 16;
        value *= 0x7feb352du;
        value ^= value >> 15;
        *out_value = (int32_t)(value % 1000u);
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_TEAM_SIDE) {
        if (binding->fighter) {
            *out_value = (int32_t)binding->fighter->owner_player + 1;
            return 1;
        }
        const ik_entity_t* e = ik_entity_get_const(
            binding->entity.pool, binding->entity.self);
        if (!e || e->owner_player >= 2u) return 0;
        *out_value = (int32_t)e->owner_player + 1;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ROUND_STATE) {
        *out_value = binding->fight->round_state;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_NUM_ENEMIES) {
        uint8_t owner = 2u;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) owner = entity->owner_player;
        }
        *out_value = owner < 2u &&
            binding->fight->fighters[owner ^ 1u].hp > 0;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_HIT_PAUSE_TIME && binding->fighter) {
        *out_value = binding->fighter->hit_pause;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_FRONT_EDGE_DIST && binding->fighter) {
        const ik_fighter_t* f = binding->fighter;
        const int32_t front_dist = f->facing > 0
            ? f->xmax_q8 - f->x_q8
            : f->x_q8 - f->xmin_q8;
        const int32_t type_offset =
            f->cur_state_type == IK_CNS_STATE_AIR ? IK_CNS_Q8_ONE / 2
            : f->cur_state_type == IK_CNS_STATE_LIEDOWN
                ? IK_CNS_Q8_ONE : 0;
        *out_value = (front_dist - f->edge_front * IK_CNS_Q8_ONE -
                      type_offset) / IK_CNS_Q8_ONE;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ANIM_ELEM_TIME && index >= 1 &&
        index <= UINT16_MAX) {
        int16_t anim = -1;
        uint16_t anim_time = 0u;
        uint8_t owner = 2u;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
            anim = binding->fighter->anim;
            anim_time = binding->fighter->anim_time;
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) {
                owner = entity->anim_owner;
                anim = entity->anim_no;
                anim_time = entity->anim_time;
            }
        }
        if (owner >= 2u) return 0;
        *out_value = ik_anim_elem_time(
            binding->fight->player_frames[owner], anim, anim_time,
            (uint16_t)index);
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_MOVE_REVERSED && binding->fighter) {
        *out_value = binding->fighter->reversed != 0u;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_MOVE_HIT && binding->fighter) {
        *out_value = binding->fighter->move_hit != 0u;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF && binding->fighter) {
        const ik_fighter_t* f = binding->fighter;
        switch ((ik_expr_field_t)field) {
            case IK_EXPR_FIELD_GET_HIT_ANIM_TYPE:
                *out_value = f->gethit_anim_type;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_GROUND_TYPE:
                *out_value = f->gethit_ground_type;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_SLIDE_TIME:
                *out_value = f->hit_slide_time;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_CTRL_TIME:
                *out_value = f->hit_ctrl_time;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_XVEL_Q8:
                *out_value = f->gethit_vx_q8;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_YVEL_Q8:
                *out_value = f->gethit_vy_q8;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_YACCEL_Q16:
                *out_value = f->gethit_yaccel_q16;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_FALL:
                *out_value = f->gethit_fall != 0u;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_FALL_XVEL_Q8:
                *out_value = f->gethit_fall_x_q8;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_FALL_YVEL_Q8:
                *out_value = f->gethit_fall_y_q8;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_FALL_RECOVER:
                *out_value = f->gethit_fall_recover != 0u;
                return 1;
            case IK_EXPR_FIELD_HIT_OVER:
                *out_value = f->hitstun == 0u;
                return 1;
            case IK_EXPR_FIELD_IN_GUARD_DIST:
                *out_value = f->in_guard_dist != 0u;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_IS_BOUND:
                *out_value = f->bound_to >= 0 ||
                    ik_entity_handle_is_valid(f->bound_entity);
                return 1;
            default:
                break;
        }
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ANIM_TIME && binding->fighter) {
        *out_value = binding->fighter->anim_time;
        return 1;
    }
    return ik_entity_expr_read_field(
        (void*)&binding->entity, redirect, field, index,
        redirect_id, redirect_index, out_value);
}

static int ikf_expr_read_command(
    void* user, uint16_t command_id, int32_t* out_value
) {
    if (!user || !out_value || command_id >= 128u) return 0;
    const ikf_expr_binding_t* binding =
        (const ikf_expr_binding_t*)user;
    const ik_fighter_t* fighter = binding->fighter;
    if (!fighter) {
        const ik_entity_t* entity = ik_entity_get_const(
            binding->entity.pool, binding->entity.self);
        if (!entity || entity->owner_player >= 2u) return 0;
        fighter = &binding->fight->fighters[entity->owner_player];
    }
    *out_value = (int32_t)(
        (fighter->command_active[command_id / 64u] >>
         (command_id % 64u)) & 1u);
    return 1;
}

int ikf_eval_cns_expr(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int32_t* out_value
) {
    if (!fight || !fighter || !cns || !out_value || !count ||
        !fight->entities || !cns->expressions ||
        (uint32_t)offset + count > cns->expression_count) return 0;
    ikf_expr_binding_t binding = {
        fight, fighter,
        {fight->entities, ikf_fighter_entity_handle(fight, fighter)}
    };
    const ik_expr_context_t expression = {
        &binding, ikf_expr_read_field, ikf_expr_read_command
    };
    return ik_expr_eval(cns->expressions + offset, count,
                        &expression, out_value);
}

int ikf_eval_cns_entity_expr(
    const ik_fight_t* fight,
    const ik_entity_t* entity,
    const ik_cns_asset_t* cns,
    uint16_t offset,
    uint8_t count,
    int32_t* out_value
) {
    if (!fight || !entity || !cns || !out_value || !count ||
        !fight->entities || !cns->expressions ||
        (uint32_t)offset + count > cns->expression_count) return 0;
    uint8_t slot = IK_ENTITY_CAPACITY;
    for (uint8_t i = 0u; i < IK_ENTITY_CAPACITY; ++i) {
        if (&fight->entities->entities[i] == entity) {
            slot = i;
            break;
        }
    }
    if (slot >= IK_ENTITY_CAPACITY) return 0;
    const ik_entity_handle_t handle = {
        slot, fight->entities->generations[slot]
    };
    ikf_expr_binding_t binding = {
        fight, 0, {fight->entities, handle}
    };
    const ik_expr_context_t expression = {
        &binding, ikf_expr_read_field, ikf_expr_read_command
    };
    return ik_expr_eval(cns->expressions + offset, count,
                        &expression, out_value);
}

static int state_power_add(
    const ik_fight_t* fight,
    const ik_fighter_t* fighter,
    const ik_cns_asset_t* cns,
    const ik_cns_state_t* spec
) {
    if (!spec->power_add_expr_count) return spec->power_add;
    int32_t value = 0;
    if (!ikf_eval_cns_expr(fight, fighter, cns,
                           spec->power_add_expr_ofs,
                           spec->power_add_expr_count, &value)) return 0;
    return value;
}

uint8_t ik_fight_state_type(const ik_fight_t* fight,
                            const ik_fighter_t* fighter) {
    (void)fight;
    return fighter ? fighter->cur_state_type : IK_CNS_STATE_UNCHANGED;
}

int ik_action_for_state(const ik_cns_asset_t* cns, int16_t state) {
    const ik_cns_state_t* spec = ik_cns_find_state(cns, state);
    if (spec) return spec->anim;

    switch (state) {
        case IK_STATE_WALK: return 20;
        case IK_STATE_CROUCH: return 11;
        case IK_STATE_JUMP: return 41;
        case IK_STATE_HIT: return 105;
        case IK_STATE_KO: return 120;
        case IK_STATE_GUARD: return 130;
        default: return 0;
    }
}

static int default_ctrl_for_state(int16_t state) {
    return state == IK_STATE_IDLE || state == IK_STATE_WALK ||
           state == IK_STATE_CROUCH || state == IK_STATE_JUMP;
}

/* Upstream stateChange1: only the state number and its clocks change. */
static void change_state_number(ik_fighter_t* f, int16_t state) {
    f->prev_state = f->state;
    f->state = state;
    f->state_time = 0u;
    ++f->state_entries;
    f->pause_fired = 0u;
    f->one_shot_controller_mask = 0u;
}

/* Fallback state type for characters without a compiled StateDef. */
static uint8_t legacy_state_type(const ik_fighter_t* f) {
    if (!f->on_ground) return IK_CNS_STATE_AIR;
    if (f->state == IK_STATE_CROUCH) return IK_CNS_STATE_CROUCH;
    return IK_CNS_STATE_STAND;
}

/* Upstream stateChange2: the StateDef parameters (anim, ctrl, velset, type,
 * movetype...) take effect. */
void ikf_init_statedef(ik_fight_t* fight, ik_fighter_t* f) {
    const ik_cns_asset_t* state_cns = cns_for_fighter(fight, f);
    const ik_cns_state_t* spec = ik_cns_find_state(state_cns, f->state);

    f->statedef_pending = 0u;
    f->physics_override = -1;
    if (spec && spec->anim_expr_count) {
        int32_t dynamic_anim = -1;
        if (ikf_eval_cns_expr(
                fight, f, state_cns, spec->anim_expr_ofs,
                spec->anim_expr_count, &dynamic_anim) &&
            dynamic_anim >= INT16_MIN && dynamic_anim <= INT16_MAX) {
            f->anim = (int16_t)dynamic_anim;
        }
        f->anim_owner = f->owner_player;
        f->anim_time = 0u;
    } else if (!(spec && spec->anim < 0)) {
        f->anim = (int16_t)ik_action_for_state(state_cns, f->state);
        f->anim_owner = f->owner_player;
        f->anim_time = 0u;
    }
    f->move_contact = 0u;
    f->move_hit = 0u;
    f->move_contact_time = 0u;
    if (!(spec && spec->hitdef_persist)) {
        f->hitdef_hit_mask = 0u;
        f->active_hitdef_local = -1;
        f->active_hitdef_global = -1;
        f->active_hitdef_secondary = 0u;
        f->hitdef_target = -1;
    }
    f->state_axis = 0;

    if (spec && spec->move_type == IK_CNS_MOVE_ATTACK) ++f->attack_id;

    if (!spec) {
        f->ctrl = (int8_t)default_ctrl_for_state(f->state);
        f->spr_priority = 0;
        f->cur_state_type = legacy_state_type(f);
        f->cur_move_type = IK_CNS_MOVE_IDLE;
        return;
    }

    int power = (int)f->power + state_power_add(fight, f, state_cns, spec);
    if (power < 0) power = 0;
    if (power > IK_MAX_POWER) power = IK_MAX_POWER;
    f->power = (int16_t)power;
    if (spec->ctrl >= 0) f->ctrl = spec->ctrl;
    f->spr_priority = spec->spr_priority;
    if (spec->state_type != IK_CNS_STATE_UNCHANGED) {
        f->cur_state_type = (uint8_t)spec->state_type;
    }
    if (spec->move_type != IK_CNS_MOVE_UNCHANGED) {
        f->cur_move_type = (uint8_t)spec->move_type;
    }
    if (f->cur_move_type != IK_CNS_MOVE_HIT && !f->reversed) {
        ikf_exit_target(fight, f);
    }
    if (spec->state_type == IK_CNS_STATE_AIR) {
        f->on_ground = 0;
    } else if (spec->state_type == IK_CNS_STATE_STAND ||
               spec->state_type == IK_CNS_STATE_CROUCH ||
               spec->state_type == IK_CNS_STATE_LIEDOWN) {
        f->on_ground = 1;
    }
    if (spec->has_velset) {
        /* StateDef velset is local: forward is where the fighter faces. */
        int32_t velocity = 0;
        f->vx_q8 = spec->velset_x_expr_count &&
                   ikf_eval_cns_expr(
                       fight, f, state_cns, spec->velset_x_expr_ofs,
                       spec->velset_x_expr_count, &velocity)
            ? (velocity / 256) * f->facing
            : spec->velset_x_q8 * f->facing;
        f->vy_q8 = spec->velset_y_expr_count &&
                   ikf_eval_cns_expr(
                       fight, f, state_cns, spec->velset_y_expr_ofs,
                       spec->velset_y_expr_count, &velocity)
            ? velocity / 256 : spec->velset_y_q8;
    }
}

void ikf_auto_turn(ik_fight_t* fight, ik_fighter_t* f) {
    const ik_cns_state_t* spec = fighter_state_spec(fight, f);
    if (spec && (spec->assert_special_flags &
                 IK_CNS_STATE_ASSERT_NO_AUTO_TURN) != 0u) {
        return;
    }
    const ik_fighter_t* foe = f == &fight->fighters[0]
        ? &fight->fighters[1] : &fight->fighters[0];
    /* Upstream: the foe is behind (distance along facing < 0). */
    if ((int64_t)(foe->x_q8 - f->x_q8) * f->facing >= 0) return;
    if (f->cur_state_type == IK_CNS_STATE_STAND && f->anim != 5) {
        f->anim = 5;
        f->anim_time = 0u;
    } else if (f->cur_state_type == IK_CNS_STATE_CROUCH && f->anim != 6) {
        f->anim = 6;
        f->anim_time = 0u;
    }
    f->facing = (int8_t)-f->facing;
}

void ikf_turn_before_change(ik_fight_t* fight, ik_fighter_t* f) {
    /* Mugen-compat quirk upstream keeps for non-Ikemen chars: a controller
     * ChangeState with ctrl during the fight turns the fighter first. */
    if (f->ctrl && fight->round_state <= 2u &&
        (f->cur_state_type == IK_CNS_STATE_STAND ||
         f->cur_state_type == IK_CNS_STATE_CROUCH)) {
        ikf_auto_turn(fight, f);
    }
}

/* ChangeState from the fighter's own controllers: the new state's StateDef
 * applies at once and its controllers run in the same tick. */
void ikf_enter_state(ik_fight_t* fight, ik_fighter_t* f, int16_t state) {
    /* The old state's VelAdd already ran this tick; that accumulates across
     * a chain of ChangeStates. */
    const int32_t ran = ikf_pre_move_gravity(fight, f);
    if (ran != 0) {
        f->gravity_carry = 1u;
        f->gravity_carry_q16 += ran;
    }
    change_state_number(f, state);
    ikf_init_statedef(fight, f);
}

/* ChangeState from outside the fighter's own tick (hit detection, landing):
 * only the number changes now; the StateDef applies when the fighter next
 * acts, as in upstream. */
void ikf_enter_state_deferred(
    ik_fight_t* fight, ik_fighter_t* f, int16_t state
) {
    (void)fight;
    change_state_number(f, state);
    f->statedef_pending = 1u;
}

int ikf_dispatch_controlled_input(ik_fight_t* fight, ik_fighter_t* f,
                                     const ik_fight_controls_t* controls) {
    if (!controls) return 0;
    const ik_cns_asset_t* native_cns =
        cns_for_owner(fight, f->owner_player);

    /* State -1 gates execute before ctrl: legal cancels can intentionally
     * ChangeState while the current attack still has ctrl = 0. */
    if (controls->has_state_request) {
        ikf_turn_before_change(fight, f);
        ikf_enter_state(fight, f, controls->requested_state);
        return 1;
    }

    if (!f->on_ground) {
        const ik_cns_constants_t* c =
            constants_for_fighter(fight, f);
        if (f->ctrl && controls->up && !f->up_latched && c &&
            c->air_jump_num > 0 &&
            f->air_jumps_used < (uint8_t)c->air_jump_num &&
            ((int32_t)IK_FLOOR_Y * IK_CNS_Q8_ONE - f->y_q8) >=
                (int32_t)c->air_jump_height * IK_CNS_Q8_ONE &&
            ik_cns_find_state(native_cns, 45)) {
            ikf_enter_state(fight, f, 45);
            f->air_jumps_used++;
            f->up_latched = 1u;
            return 1;
        }
        return 0;
    }

    if (!f->ctrl) return 0;
    if (controls->down) {
        const int16_t crouch_state =
            ik_cns_find_state(native_cns, 10)
                ? 10
                : IK_STATE_CROUCH;
        if (f->cur_state_type == IK_CNS_STATE_STAND &&
            f->state != IK_STATE_CROUCH && f->state != crouch_state) {
            /* Upstream's hardcoded stand-to-crouch stops the fighter dead,
             * except when braking out of a run (state 100). */
            if (f->state != 100) f->vx_q8 = 0;
            ikf_enter_state(fight, f, crouch_state);
            return 1;
        }
        return 0;
    }
    /* Upstream stands up from any crouching state that has ctrl. */
    if (!controls->down && f->cur_state_type == IK_CNS_STATE_CROUCH &&
        f->state != 12 && ik_cns_find_state(native_cns, 12)) {
        ikf_enter_state(fight, f, 12);
        return 1;
    }
    if (controls->up &&
        ik_cns_find_state(native_cns, IK_STATE_JUMP)) {
        ikf_enter_state(fight, f, IK_STATE_JUMP);
        f->up_latched = 1u;
        return 1;
    }
    return 0;
}
