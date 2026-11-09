#include "ikemen_saturn/ikemen_character_bundle.h"

#include <stddef.h>

#define IKCB_HEADER_BYTES 20u
#define IKCB_ENTRY_BYTES 16u

static uint16_t read_be16(const uint8_t* p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}

static uint32_t read_be32(const uint8_t* p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static void clear_bytes(void* data, uint32_t bytes) {
    uint8_t* output = (uint8_t*)data;
    for (uint32_t i = 0u; i < bytes; ++i) output[i] = 0u;
}

static const ik_character_bundle_entry_t* find_section(
    const ik_character_bundle_view_t* view, uint16_t id
) {
    if (!view) return NULL;
    for (uint16_t i = 0u; i < view->section_count; ++i) {
        if (view->sections[i].id == id) return &view->sections[i];
    }
    return NULL;
}

int ik_character_bundle_open(
    const void* data, uint32_t bytes,
    ik_character_bundle_view_t* out_view
) {
    static const uint8_t magic[8] = {
        'I', 'K', 'B', 'N', 'D', 'L', 0, 0
    };
    if (!data || !out_view || bytes < IKCB_HEADER_BYTES) return 0;
    const uint8_t* raw = (const uint8_t*)data;
    for (uint8_t i = 0u; i < (uint8_t)sizeof(magic); ++i) {
        if (raw[i] != magic[i]) return 0;
    }
    if (read_be16(raw + 8u) != IK_CHARACTER_BUNDLE_VERSION) return 0;
    const uint16_t section_count = read_be16(raw + 10u);
    const uint32_t directory_offset = read_be32(raw + 12u);
    const uint32_t total_bytes = read_be32(raw + 16u);
    if (section_count > IK_CHARACTER_BUNDLE_MAX_SECTIONS ||
        directory_offset != IKCB_HEADER_BYTES || total_bytes != bytes) {
        return 0;
    }
    const uint32_t directory_bytes =
        (uint32_t)section_count * IKCB_ENTRY_BYTES;
    if (directory_bytes > bytes - directory_offset) return 0;
    const uint32_t payload_min = directory_offset + directory_bytes;

    ik_character_bundle_view_t result;
    clear_bytes(&result, (uint32_t)sizeof(result));
    result.data = raw;
    result.bytes = bytes;
    result.section_count = section_count;
    for (uint16_t i = 0u; i < section_count; ++i) {
        const uint8_t* entry = raw + directory_offset +
                               (uint32_t)i * IKCB_ENTRY_BYTES;
        ik_character_bundle_entry_t* out = &result.sections[i];
        out->id = read_be16(entry);
        out->alignment = read_be16(entry + 2u);
        out->count = read_be32(entry + 4u);
        out->offset = read_be32(entry + 8u);
        out->bytes = read_be32(entry + 12u);
        if (out->id == 0u ||
            (out->alignment != 1u && out->alignment != 2u &&
             out->alignment != 4u && out->alignment != 8u &&
             out->alignment != 16u && out->alignment != 32u) ||
            out->offset < payload_min || out->offset > bytes ||
            out->bytes > bytes - out->offset ||
            (out->offset & (out->alignment - 1u)) != 0u ||
            (((uintptr_t)(raw + out->offset)) &
             (uintptr_t)(out->alignment - 1u)) != 0u) {
            return 0;
        }
        for (uint16_t j = 0u; j < i; ++j) {
            const ik_character_bundle_entry_t* prior = &result.sections[j];
            if (prior->id == out->id) return 0;
            if (prior->bytes != 0u && out->bytes != 0u &&
                prior->offset < out->offset + out->bytes &&
                out->offset < prior->offset + prior->bytes) {
                return 0;
            }
        }
    }
    *out_view = result;
    return 1;
}

int ik_character_bundle_get_table(
    const ik_character_bundle_view_t* view,
    uint16_t section_id, uint32_t item_bytes,
    const void** out_data, uint32_t* out_count
) {
    if (!view || !out_data || !out_count || item_bytes == 0u) return 0;
    const ik_character_bundle_entry_t* entry =
        find_section(view, section_id);
    if (!entry) return 0;
    const uint64_t required = (uint64_t)entry->count * item_bytes;
    if (required > UINT32_MAX ||
        (entry->count != 0u && entry->bytes != (uint32_t)required)) {
        return 0;
    }
    *out_count = entry->count;
    *out_data = entry->count == 0u ? NULL : view->data + entry->offset;
    return 1;
}

int ik_character_bundle_bind_cns(
    const ik_character_bundle_view_t* view,
    ik_cns_asset_t* out_cns
) {
    if (!view || !out_cns) return 0;
    const void* table = NULL;
    uint32_t count = 0u;
    if (!ik_character_bundle_get_table(
            view, IK_CHARACTER_BUNDLE_CNS_CONSTANTS,
            sizeof(ik_cns_constants_t), &table, &count) || count != 1u) {
        return 0;
    }
    ik_cns_asset_t result;
    clear_bytes(&result, (uint32_t)sizeof(result));
    const uint8_t* constants = (const uint8_t*)table;
    uint8_t* destination = (uint8_t*)&result.constants;
    for (uint32_t i = 0u; i < (uint32_t)sizeof(result.constants); ++i) {
        destination[i] = constants[i];
    }

#define IKCB_BIND_TABLE(section_id, item_type, member, count_member) \
    do { \
        if (!ik_character_bundle_get_table( \
                view, (section_id), sizeof(item_type), &table, &count) || \
            count > UINT16_MAX) { \
            return 0; \
        } \
        result.member = (const item_type*)table; \
        result.count_member = (uint16_t)count; \
    } while (0)

    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_STATES, ik_cns_state_t,
                    states, state_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_HITDEFS, ik_cns_hitdef_t,
                    hitdefs, hitdef_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_PLAYSNDS, ik_cns_playsnd_t,
                    playsnds, playsnd_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_CONTROLLERS,
                    ik_cns_controller_t, controllers, controller_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_HELPERS, ik_cns_helper_t,
                    helpers, helper_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_REVERSALS,
                    ik_cns_reversaldef_t, reversals, reversal_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_HITOVERRIDES,
                    ik_cns_hitoverride_t, hitoverrides, hitoverride_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_EXPLODS, ik_cns_explod_t,
                    explods, explod_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_PROJECTILES,
                    ik_cns_projectile_t, projectiles, projectile_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_PROJECTILE_MODS,
                    ik_cns_projectile_mod_t, projectile_mods,
                    projectile_mod_count);
    IKCB_BIND_TABLE(IK_CHARACTER_BUNDLE_CNS_EXPRESSIONS, ik_expr_instr_t,
                    expressions, expression_count);
#undef IKCB_BIND_TABLE

    *out_cns = result;
    return 1;
}
