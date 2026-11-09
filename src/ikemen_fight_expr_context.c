/* Bind CNS expressions to live fighter and entity state. */
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
    if (field == IK_EXPR_FIELD_HITDEF_ATTR) {
        uint8_t owner = 2u;
        int16_t active_hitdef = -1;
        const ik_cns_asset_t* asset = 0;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
            active_hitdef = binding->fighter->active_hitdef_global;
            asset = cns_for_fighter(binding->fight, binding->fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) {
                owner = entity->owner_player;
                active_hitdef = entity->active_hitdef_global;
                asset = cns_for_owner(
                    binding->fight, entity->state_owner);
            }
        }
        if (redirect == IK_EXPR_REDIRECT_P2) owner ^= 1u;
        else if (redirect != IK_EXPR_REDIRECT_SELF) return 0;
        if (owner >= 2u) return 0;
        if (redirect == IK_EXPR_REDIRECT_P2) {
            const ik_fighter_t* opponent =
                &binding->fight->fighters[owner];
            active_hitdef = opponent->active_hitdef_global;
            asset = cns_for_fighter(binding->fight, opponent);
        }
        if (!asset || active_hitdef < 0 ||
            active_hitdef >= (int16_t)asset->hitdef_count) {
            *out_value = 0;
            return 1;
        }
        const ik_cns_hitdef_t* hitdef =
            &asset->hitdefs[(uint16_t)active_hitdef];
        const uint16_t state_mask = (uint16_t)((uint32_t)index >> 16);
        const uint16_t attr_mask = (uint16_t)index;
        *out_value =
            (hitdef->attack_state_mask & state_mask) != 0u &&
            (hitdef->attack_attr_mask & attr_mask) != 0u;
        return 1;
    }
    if (field == IK_EXPR_FIELD_CHAR_CONSTANT) {
        const ik_entity_t* entity = 0;
        if (redirect == IK_EXPR_REDIRECT_P2) {
            uint8_t owner = 2u;
            if (binding->fighter) {
                owner = ikf_fighter_player_index(
                    binding->fight, binding->fighter);
            } else {
                const ik_entity_t* self = ik_entity_get_const(
                    binding->entity.pool, binding->entity.self);
                if (self) owner = self->owner_player;
            }
            if (owner >= 2u) return 0;
            entity = ik_entity_get_const(
                binding->entity.pool,
                binding->fight->player_entities[owner ^ 1u]);
        } else if (redirect == IK_EXPR_REDIRECT_TARGET ||
                   redirect == IK_EXPR_REDIRECT_PARENT ||
                   redirect == IK_EXPR_REDIRECT_ROOT) {
            const ik_entity_handle_t handle =
                redirect == IK_EXPR_REDIRECT_TARGET
                ? ik_entity_redirect_target(
                    binding->entity.pool, binding->entity.self, 0, 0u)
                : ik_entity_redirect(
                    binding->entity.pool, binding->entity.self, redirect);
            entity = ik_entity_get_const(binding->entity.pool, handle);
        } else if (redirect != IK_EXPR_REDIRECT_SELF) {
            return 0;
        } else if (binding->fighter) {
            const uint8_t owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
            if (owner < 2u) {
                entity = ik_entity_get_const(
                    binding->entity.pool,
                    binding->fight->player_entities[owner]);
            }
        } else {
            entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
        }
        if (!entity) return 0;
        const ik_cns_asset_t* asset =
            cns_for_owner(binding->fight, entity->state_owner);
        if (!asset) return 0;
        switch (index) {
            case 1: *out_value = asset->constants.head_pos_x; return 1;
            case 2: *out_value = asset->constants.head_pos_y; return 1;
            case 3: *out_value = asset->constants.mid_pos_x; return 1;
            case 4: *out_value = asset->constants.mid_pos_y; return 1;
            default: return 0;
        }
    }
    if (field == IK_EXPR_FIELD_LIFE_MAX) {
        uint8_t owner = 2u;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) owner = entity->owner_player;
        }
        if (redirect == IK_EXPR_REDIRECT_P2) owner ^= 1u;
        else if (redirect != IK_EXPR_REDIRECT_SELF &&
                 redirect != IK_EXPR_REDIRECT_PARENT &&
                 redirect != IK_EXPR_REDIRECT_ROOT) return 0;
        if (owner >= 2u) return 0;
        const ik_cns_asset_t* asset = cns_for_fighter(
            binding->fight, &binding->fight->fighters[owner]);
        if (!asset) return 0;
        *out_value = asset->constants.life;
        return 1;
    }
    if (field == IK_EXPR_FIELD_CHARACTER_NAME_HASH) {
        if (redirect == IK_EXPR_REDIRECT_SELF && !binding->fighter) {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity && entity->type == IK_ENTITY_HELPER &&
                entity->name_hash != 0u) {
                *out_value = (int32_t)entity->name_hash;
                return 1;
            }
        }
        uint8_t owner = 2u;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) owner = entity->owner_player;
        }
        if (redirect == IK_EXPR_REDIRECT_P2) owner ^= 1u;
        else if (redirect != IK_EXPR_REDIRECT_SELF) return 0;
        if (owner >= 2u) return 0;
        const ik_cns_asset_t* asset = cns_for_fighter(
            binding->fight, &binding->fight->fighters[owner]);
        if (!asset) return 0;
        *out_value = (int32_t)asset->constants.character_name_hash;
        return 1;
    }
    if (field == IK_EXPR_FIELD_WIN_KO) {
        uint8_t owner = 2u;
        if (binding->fighter) {
            owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) owner = entity->owner_player;
        }
        if (redirect == IK_EXPR_REDIRECT_P2) owner ^= 1u;
        else if (redirect != IK_EXPR_REDIRECT_SELF &&
                 redirect != IK_EXPR_REDIRECT_ROOT &&
                 redirect != IK_EXPR_REDIRECT_PARENT) return 0;
        if (owner >= 2u) return 0;
        *out_value = binding->fight->win_by_ko &&
            binding->fight->winner == (uint8_t)(owner + 1u);
        return 1;
    }
    if (field == IK_EXPR_FIELD_WIN_PERFECT ||
        field == IK_EXPR_FIELD_LOSE_KO) {
        uint8_t owner = 2u;
        const ik_fighter_t* fighter = binding->fighter;
        if (fighter) {
            owner = ikf_fighter_player_index(binding->fight, fighter);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) {
                owner = entity->owner_player;
                if (owner < 2u) fighter =
                    &binding->fight->fighters[owner];
            }
        }
        if (owner >= 2u) return 0;
        if (field == IK_EXPR_FIELD_WIN_PERFECT) {
            const ik_cns_asset_t* asset = cns_for_fighter(
                binding->fight, &binding->fight->fighters[owner]);
            *out_value = binding->fight->winner == (uint8_t)(owner + 1u) &&
                fighter && asset && fighter->hp >= asset->constants.life;
        } else {
            *out_value = binding->fight->win_by_ko &&
                binding->fight->winner != 0u &&
                binding->fight->winner != (uint8_t)(owner + 1u);
        }
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_ROUND_NUMBER) {
        *out_value = binding->fight->round_number;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_STAGE_AUTHOR_HASH) {
        *out_value = (int32_t)binding->fight->stage_author_hash;
        return 1;
    }
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
    if ((redirect == IK_EXPR_REDIRECT_SELF ||
         redirect == IK_EXPR_REDIRECT_ROOT) &&
        (field == IK_EXPR_FIELD_P2_DIST_X_Q8 ||
         field == IK_EXPR_FIELD_P2_DIST_Y_Q8)) {
        uint8_t owner = 2u;
        const ik_fighter_t* self = binding->fighter;
        if (self) {
            owner = ikf_fighter_player_index(binding->fight, self);
        } else {
            const ik_entity_t* entity = ik_entity_get_const(
                binding->entity.pool, binding->entity.self);
            if (entity) owner = entity->owner_player;
        }
        if (owner >= 2u) return 0;
        if (!self) self = &binding->fight->fighters[owner];
        const ik_fighter_t* foe = &binding->fight->fighters[owner ^ 1u];
        if (field == IK_EXPR_FIELD_P2_DIST_X_Q8) {
            *out_value = (foe->x_q8 - self->x_q8) * self->facing;
        } else {
            *out_value = foe->y_q8 - self->y_q8;
        }
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_P2 &&
        field == IK_EXPR_FIELD_BODY_DIST_X && binding->fighter) {
        const uint8_t owner = ikf_fighter_player_index(
            binding->fight, binding->fighter);
        if (owner >= 2u) return 0;
        const ik_fighter_t* self = binding->fighter;
        const ik_fighter_t* foe = &binding->fight->fighters[owner ^ 1u];
        int self_left = 0;
        int self_right = 0;
        int foe_left = 0;
        int foe_right = 0;
        ik_body_box(self, &self_left, 0, &self_right, 0);
        ik_body_box(foe, &foe_left, 0, &foe_right, 0);
        *out_value = self->facing >= 0
            ? foe_left - self_right
            : self_left - foe_right;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_HIT_PAUSE_TIME && binding->fighter) {
        *out_value = binding->fighter->hit_pause;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        (field == IK_EXPR_FIELD_FRONT_EDGE_DIST ||
         field == IK_EXPR_FIELD_FRONT_EDGE_BODY_DIST) && binding->fighter) {
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
        field == IK_EXPR_FIELD_BACK_EDGE_BODY_DIST && binding->fighter) {
        const ik_fighter_t* f = binding->fighter;
        int left = 0;
        int right = 0;
        ik_body_box(f, &left, 0, &right, 0);
        const int edge_left = binding->fight->xmin_q8 / IK_CNS_Q8_ONE;
        const int edge_right = binding->fight->xmax_q8 / IK_CNS_Q8_ONE;
        *out_value = f->facing >= 0
            ? left - edge_left : edge_right - right;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_HELPER &&
        field == IK_EXPR_FIELD_BACK_EDGE_DIST) {
        const ik_entity_t* self = ik_entity_get_const(
            binding->entity.pool, binding->entity.self);
        if (!self || self->owner_player >= 2u || redirect_id < 0) return 0;
        uint8_t found = 0u;
        const ik_entity_t* helper = 0;
        for (uint8_t slot = 0u; slot < IK_ENTITY_CAPACITY; ++slot) {
            const ik_entity_t* candidate =
                &binding->entity.pool->entities[slot];
            if (candidate->type != IK_ENTITY_HELPER ||
                candidate->owner_player != self->owner_player ||
                candidate->id != redirect_id) continue;
            if (found++ == redirect_index) {
                helper = candidate;
                break;
            }
        }
        if (!helper) return 0;
        const ik_fighter_t* bounds =
            &binding->fight->fighters[self->owner_player];
        const int32_t back_offset = helper->push_back * IK_CNS_Q8_ONE;
        const int32_t distance = helper->facing > 0
            ? helper->x_q8 - bounds->xmin_q8 - back_offset
            : bounds->xmax_q8 - helper->x_q8 - back_offset;
        *out_value = distance / IK_CNS_Q8_ONE;
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
        const ik_frame_table_t* frames = owner < 2u
            ? binding->fight->player_frames[owner]
            : owner == 2u ? binding->fight->fightfx_frames : 0;
        if (!frames) return 0;
        *out_value = ik_anim_elem_time(
            frames, anim, anim_time, (uint16_t)index);
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
    if (redirect == IK_EXPR_REDIRECT_SELF &&
        field == IK_EXPR_FIELD_MOVE_GUARDED && binding->fighter) {
        *out_value = binding->fighter->move_contact_type == 1u;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF && binding->fighter &&
        field == IK_EXPR_FIELD_HIT_COUNT) {
        *out_value = binding->fighter->hit_count;
        return 1;
    }
    if (redirect == IK_EXPR_REDIRECT_SELF && binding->fighter &&
        field == IK_EXPR_FIELD_UNIQ_HIT_COUNT) {
        *out_value = binding->fighter->uniq_hit_count;
        return 1;
    }
    if ((redirect == IK_EXPR_REDIRECT_SELF ||
         redirect == IK_EXPR_REDIRECT_P2) && binding->fighter) {
        const ik_fighter_t* f = binding->fighter;
        if (redirect == IK_EXPR_REDIRECT_P2) {
            const uint8_t owner = ikf_fighter_player_index(
                binding->fight, binding->fighter);
            if (owner >= 2u) return 0;
            f = &binding->fight->fighters[owner ^ 1u];
        }
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
            case IK_EXPR_FIELD_GET_HIT_HIT_COUNT:
                *out_value = f->gethit_hit_count;
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
            case IK_EXPR_FIELD_HIT_SHAKE_OVER:
                *out_value = f->hit_shake_time == 0u;
                return 1;
            case IK_EXPR_FIELD_CAN_RECOVER:
                *out_value = f->gethit_fall_recover != 0u &&
                    f->fall_time >= f->gethit_fall_recover_time;
                return 1;
            case IK_EXPR_FIELD_IN_GUARD_DIST:
                *out_value = f->in_guard_dist != 0u;
                return 1;
            case IK_EXPR_FIELD_GET_HIT_IS_BOUND:
                *out_value = f->bound_to >= 0 ||
                    ik_entity_handle_is_valid(f->bound_entity);
                return 1;
            case IK_EXPR_FIELD_GET_HIT_CHAIN_ID:
                *out_value = f->last_hit_id;
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

