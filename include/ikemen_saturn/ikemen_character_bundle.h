#ifndef IKEMEN_CHARACTER_BUNDLE_H
#define IKEMEN_CHARACTER_BUNDLE_H

#include <stdint.h>

#include "ikemen_cns.h"
#include "ikemen_frame.h"

/* On-disc directory integers are big-endian. Table bytes are target-native
 * Saturn ABI records copied from SH2 object sections. */
#define IK_CHARACTER_BUNDLE_MAGIC "IKBNDL\0\0"
#define IK_CHARACTER_BUNDLE_VERSION 1u

typedef enum ik_character_bundle_section {
    IK_CHARACTER_BUNDLE_CNS_CONSTANTS = 1,
    IK_CHARACTER_BUNDLE_CNS_STATES = 2,
    IK_CHARACTER_BUNDLE_CNS_HITDEFS = 3,
    IK_CHARACTER_BUNDLE_CNS_PLAYSNDS = 4,
    IK_CHARACTER_BUNDLE_CNS_CONTROLLERS = 5,
    IK_CHARACTER_BUNDLE_CNS_HELPERS = 6,
    IK_CHARACTER_BUNDLE_CNS_REVERSALS = 7,
    IK_CHARACTER_BUNDLE_CNS_HITOVERRIDES = 8,
    IK_CHARACTER_BUNDLE_CNS_EXPLODS = 9,
    IK_CHARACTER_BUNDLE_CNS_PROJECTILES = 10,
    IK_CHARACTER_BUNDLE_CNS_PROJECTILE_MODS = 11,
    IK_CHARACTER_BUNDLE_CNS_EXPRESSIONS = 12,
    IK_CHARACTER_BUNDLE_FRAMES = 20,
    IK_CHARACTER_BUNDLE_CLSN_BOXES = 21,
    IK_CHARACTER_BUNDLE_SPRITES = 22,
    IK_CHARACTER_BUNDLE_PALETTES = 23,
    IK_CHARACTER_BUNDLE_COMMAND_KEYS = 24,
    IK_CHARACTER_BUNDLE_COMMAND_STEPS = 25,
    IK_CHARACTER_BUNDLE_COMMAND_LOOPS = 26,
    IK_CHARACTER_BUNDLE_COMMAND_PATTERNS = 27,
    IK_CHARACTER_BUNDLE_COMMAND_NAMES = 28,
    IK_CHARACTER_BUNDLE_COMMAND_STRINGS = 29,
    IK_CHARACTER_BUNDLE_STATE_RULE_CODE = 30,
    IK_CHARACTER_BUNDLE_STATE_RULES = 31
} ik_character_bundle_section_t;

#define IK_CHARACTER_BUNDLE_MAX_SECTIONS 32u

typedef struct ik_character_bundle_entry {
    uint16_t id;
    uint16_t alignment;
    uint32_t count;
    uint32_t offset;
    uint32_t bytes;
} ik_character_bundle_entry_t;

typedef struct ik_character_bundle_view {
    const uint8_t* data;
    uint32_t bytes;
    uint16_t section_count;
    ik_character_bundle_entry_t sections[IK_CHARACTER_BUNDLE_MAX_SECTIONS];
} ik_character_bundle_view_t;

typedef struct ik_character_bundle_graphics {
    ik_frame_table_t frames;
    const ik_sprite_source_t* sprites;
    uint32_t sprite_count;
    const uint16_t** palettes;
    uint16_t palette_count;
} ik_character_bundle_graphics_t;

/* Pointer-free on-disc form of ik_cmd_name_t. name_offset is relative to the
 * COMMAND_STRINGS section; the other fields match the runtime record. */
typedef struct ik_character_bundle_command_name {
    uint32_t name_offset;
    uint16_t pattern_ofs;
    uint8_t pattern_count;
    uint8_t reserved;
} ik_character_bundle_command_name_t;

/* Opens and validates a versioned target-native bundle directory. Payload
 * arrays remain in caller-owned memory; keep it resident while using them. */
int ik_character_bundle_open(
    const void* data, uint32_t bytes,
    ik_character_bundle_view_t* out_view);

/* Returns a validated table pointer and count. A zero-count optional table
 * returns NULL with count zero. item_bytes must match the native record size. */
int ik_character_bundle_get_table(
    const ik_character_bundle_view_t* view,
    uint16_t section_id, uint32_t item_bytes,
    const void** out_data, uint32_t* out_count);

int ik_character_bundle_get_section(
    const ik_character_bundle_view_t* view,
    uint16_t section_id, const void** out_data,
    uint32_t* out_count, uint32_t* out_bytes);

/* Binds CNS arrays directly into bundle storage and copies the constants
 * record into the caller-owned root asset. */
int ik_character_bundle_bind_cns(
    const ik_character_bundle_view_t* view,
    ik_cns_asset_t* out_cns);

int ik_character_bundle_bind_graphics(
    const ik_character_bundle_view_t* view,
    ik_character_bundle_graphics_t* out_graphics,
    const uint16_t** palette_storage,
    uint16_t palette_capacity);

int ik_character_bundle_bind_commands(
    const ik_character_bundle_view_t* view,
    ik_command_asset_t* out_commands,
    ik_cmd_name_t* name_storage,
    uint16_t name_capacity);

int ik_character_bundle_bind_state_rules(
    const ik_character_bundle_view_t* view,
    ik_state_rule_asset_t* out_state_rules);

#endif /* IKEMEN_CHARACTER_BUNDLE_H */
