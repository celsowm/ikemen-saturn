/* End-to-end host contract for the generated Ikemen KFM assets.
 *
 * Checks that the generated frame tables, the packed sprite blobs that ship on
 * the disc and the runtime decoder agree: every sprite in every table decodes
 * from its blob, offsets/sizes stay inside the blob, and the frame metadata is
 * consistent with the sprite source it points at.
 *
 * The tables and blobs are build outputs (cmake builds them from the pinned
 * external data); IKEMEN_ISO_DIR names the directory holding the .BIN blobs.
 * Texture upload and drawing belong to LibSaturn and are covered by its own
 * tests, so this contract deliberately uses no library internals.
 */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "ikemen_anim.h"
#include "ikemen_cns.h"
#include "ikemen_saturn/kfm_cns.h"
#include "ikemen_saturn/kfm_zss_cns.h"
#include "ikemen_saturn/fightfx_frames.h"
#include "ikemen_saturn/kfm_frames.h"
#include "ikemen_saturn/kfm_zss_frames.h"

#define OK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x); std::exit(1); } } while(0)

static std::vector<uint8_t> load_sprite_blob(const std::string& path) {
    std::FILE* file = std::fopen(path.c_str(), "rb");
    if (!file) std::fprintf(stderr, "cannot open %s\n", path.c_str());
    OK(file != nullptr);
    OK(std::fseek(file, 0, SEEK_END) == 0);
    const long size = std::ftell(file);
    OK(size >= 0);
    OK(std::fseek(file, 0, SEEK_SET) == 0);
    std::vector<uint8_t> blob(static_cast<size_t>(size));
    OK(blob.empty() ||
       std::fread(blob.data(), 1u, blob.size(), file) == blob.size());
    OK(std::fclose(file) == 0);
    return blob;
}

static std::string iso_dir() {
    const char* env = std::getenv("IKEMEN_ISO_DIR");
    return env && *env ? env : "generated/ikemen_saturn/iso";
}

/* Decode every sprite of one table from its blob. Returns the number of
 * distinct sprite indices referenced by the frame table. */
static uint32_t check_table(const ik_frame_t* frames, uint32_t frame_count,
                            const ik_sprite_source_t* sprites,
                            uint32_t sprite_count, uint32_t data_bytes,
                            const std::vector<uint8_t>& blob,
                            uint8_t* scratch, uint32_t scratch_size) {
    OK(blob.size() == data_bytes);
    std::vector<bool> referenced(sprite_count, false);
    for (uint32_t i = 0; i < frame_count; ++i) {
        const ik_frame_t& f = frames[i];
        OK((f.w & 7u) == 0u);
        OK(f.w >= 8u && f.w <= 504u);
        OK(f.h >= 1u && f.h <= 255u);
        OK(f.sprite_index < sprite_count);
        const ik_sprite_source_t& sprite = sprites[f.sprite_index];
        OK(sprite.padded_w == f.w);
        OK(sprite.source_h == f.h);
        referenced[f.sprite_index] = true;
    }
    uint32_t used = 0u;
    for (uint32_t s = 0; s < sprite_count; ++s) {
        const ik_sprite_source_t& sprite = sprites[s];
        OK((sprite.data_ofs & 3u) == 0u);
        OK(sprite.data_ofs <= data_bytes);
        OK(sprite.data_size <= data_bytes - sprite.data_ofs);
        if (!referenced[s]) continue;
        ++used;
        OK(ik_sprite_decode(&sprite, blob.data(),
                            static_cast<uint32_t>(blob.size()),
                            scratch, scratch_size) != 0);
    }
    return used;
}

int main() {
    const std::string dir = iso_dir();
    const std::vector<uint8_t> sprite_blob = load_sprite_blob(dir + "/KFM_SPR.BIN");
    const std::vector<uint8_t> zss_blob = load_sprite_blob(dir + "/KFM_ZSS.BIN");
    const std::vector<uint8_t> fightfx_blob = load_sprite_blob(dir + "/FIGHTFX.BIN");

    OK(KFM_CLSN_BOX_COUNT > 0u);
    OK(KFM_SPRITE_DATA_BYTES < KFM_RAW_PIXELS_BYTES);
    OK(KFM_ZSS_SPRITE_DATA_BYTES < KFM_ZSS_RAW_PIXELS_BYTES);

    static uint8_t kfm_scratch[KFM_MAX_SPRITE_BYTES];
    const uint32_t unique = check_table(
        kfm_frames, KFM_FRAME_COUNT, kfm_sprites, KFM_SPRITE_COUNT,
        KFM_SPRITE_DATA_BYTES, sprite_blob, kfm_scratch, sizeof(kfm_scratch));

    static uint8_t zss_scratch[KFM_ZSS_MAX_SPRITE_BYTES];
    check_table(kfm_zss_frames, KFM_ZSS_FRAME_COUNT, kfm_zss_sprites,
                KFM_ZSS_SPRITE_COUNT, KFM_ZSS_SPRITE_DATA_BYTES, zss_blob,
                zss_scratch, sizeof(zss_scratch));

    static uint8_t fx_scratch[FIGHTFX_MAX_SPRITE_BYTES];
    check_table(fightfx_frames, FIGHTFX_FRAME_COUNT, fightfx_sprites,
                FIGHTFX_SPRITE_COUNT, FIGHTFX_SPRITE_DATA_BYTES, fightfx_blob,
                fx_scratch, sizeof(fx_scratch));

    /* Check the actual compiled CNS table linked into the Saturn firmware,
     * not only the Python importer report. Eight state bodies now come
     * from verified ZSS sources; unported states keep the fallback. */
    struct ExpectedZss {
        int16_t state;
        uint8_t count;
        uint8_t first_type;
        uint8_t last_type;
    };
    const ExpectedZss expected_zss[] = {
        {170, 1u, IK_CNS_CTRL_NOT_HIT_BY, IK_CNS_CTRL_NOT_HIT_BY},
        {180, 1u, IK_CNS_CTRL_CHANGE_STATE, IK_CNS_CTRL_CHANGE_STATE},
        {820, 2u, IK_CNS_CTRL_CHANGE_ANIM2, IK_CNS_CTRL_SELF_STATE},
        {1025, 2u, IK_CNS_CTRL_CHANGE_ANIM2, IK_CNS_CTRL_CHANGE_STATE},
        {821, 4u, IK_CNS_CTRL_VEL_ADD, IK_CNS_CTRL_SELF_STATE},
        {1026, 5u, IK_CNS_CTRL_HIT_VEL_SET, IK_CNS_CTRL_SELF_STATE},
        {1028, 7u, IK_CNS_CTRL_NOT_HIT_BY, IK_CNS_CTRL_SELF_STATE},
        {1027, 8u, IK_CNS_CTRL_TURN, IK_CNS_CTRL_CHANGE_STATE},
    };
    for (const ExpectedZss& expected : expected_zss) {
        const ik_cns_state_t* state = ik_cns_find_state(
            &kfm_zss_cns, expected.state);
        OK(state != nullptr);
        OK(state->controller_count == expected.count);
        OK(static_cast<uint32_t>(state->controller_ofs) + expected.count <=
           kfm_zss_cns.controller_count);
        const ik_cns_controller_t* cs =
            kfm_zss_cns.controllers + state->controller_ofs;
        OK(cs[0].type == expected.first_type);
        OK(cs[expected.count - 1u].type == expected.last_type);
        const ik_cns_state_t* classic =
            ik_cns_find_state(&kfm_cns, expected.state);
        OK(classic != nullptr);
    }
    /* State 600 is still a classic CNS HitDef/sound fallback, but its
     * original ZSS CtrlSet must use AnimElemTime(3)=2, not Time=17.
     * Assert both generated character bundles stay independent. */
    const ik_cns_state_t* classic600 = ik_cns_find_state(&kfm_cns, 600);
    const ik_cns_state_t* zss600 = ik_cns_find_state(&kfm_zss_cns, 600);
    OK(classic600 != nullptr && zss600 != nullptr);
    const ik_cns_controller_t* classic600_ctrl = nullptr;
    const ik_cns_controller_t* zss600_ctrl = nullptr;
    for (unsigned i = 0u; i < classic600->controller_count; ++i) {
        const ik_cns_controller_t* ctrl =
            &kfm_cns.controllers[classic600->controller_ofs + i];
        if (ctrl->type == IK_CNS_CTRL_CTRL_SET) classic600_ctrl = ctrl;
    }
    for (unsigned i = 0u; i < zss600->controller_count; ++i) {
        const ik_cns_controller_t* ctrl =
            &kfm_zss_cns.controllers[zss600->controller_ofs + i];
        if (ctrl->type == IK_CNS_CTRL_CTRL_SET) zss600_ctrl = ctrl;
    }
    OK(classic600_ctrl != nullptr && zss600_ctrl != nullptr);
    OK(classic600_ctrl->trigger_kind == IK_CNS_TRIGGER_TIME_EQ);
    OK(classic600_ctrl->trigger_value == 17);
    OK(zss600_ctrl->trigger_kind == IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED);
    OK(zss600_ctrl->trigger_value == ((3 << 8) | 2));
    ik_cns_controller_context_t air_ctx{};
    air_ctx.anim_element = 3u;
    air_ctx.anim_element_time = 2u;
    OK(ik_cns_controller_trigger_context_now(zss600_ctrl, &air_ctx));
    air_ctx.anim_element_time = 1u;
    OK(!ik_cns_controller_trigger_context_now(zss600_ctrl, &air_ctx));

    const ik_cns_state_t* zss170 = ik_cns_find_state(&kfm_zss_cns, 170);
    OK(zss170->anim == 170);
    const ik_cns_state_t* zss180 = ik_cns_find_state(&kfm_zss_cns, 180);
    OK(zss180->anim == -2);
    const ik_cns_controller_t* win =
        &kfm_zss_cns.controllers[zss180->controller_ofs];
    OK(win->value0 == 181);
    OK((win->flags & IK_CNS_CTRL_HAS_CTRL) != 0u);
    const ik_cns_state_t* zss820 = ik_cns_find_state(&kfm_zss_cns, 820);
    const ik_cns_controller_t* thrown =
        kfm_zss_cns.controllers + zss820->controller_ofs;
    OK(thrown[0].trigger_kind == IK_CNS_TRIGGER_TIME_EQ);
    OK(thrown[0].value0 == 820);
    OK(thrown[1].trigger_kind == IK_CNS_TRIGGER_NOT_BOUND);
    OK(thrown[1].value0 == 5050);
    const ik_cns_state_t* zss1025 = ik_cns_find_state(&kfm_zss_cns, 1025);
    const ik_cns_controller_t* palm =
        kfm_zss_cns.controllers + zss1025->controller_ofs;
    OK(palm[1].trigger_kind == IK_CNS_TRIGGER_HIT_SHAKE_OVER);
    OK(palm[1].value0 == 1026);
    const ik_cns_state_t* zss821 = ik_cns_find_state(&kfm_zss_cns, 821);
    const ik_cns_controller_t* airborne =
        kfm_zss_cns.controllers + zss821->controller_ofs;
    OK(airborne[0].value5 != 0);
    OK(airborne[1].trigger_kind == IK_CNS_TRIGGER_THROW_GROUND_RECOVERY);
    OK(airborne[1].value0 == 5200);
    OK(airborne[2].trigger_kind == IK_CNS_TRIGGER_THROW_AIR_RECOVERY);
    OK(airborne[2].value0 == 5210);
    OK(airborne[3].trigger_kind == IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR);
    OK(airborne[3].value0 == 5100);
    const ik_cns_state_t* zss1026 = ik_cns_find_state(&kfm_zss_cns, 1026);
    const ik_cns_controller_t* wall =
        kfm_zss_cns.controllers + zss1026->controller_ofs;
    OK(wall[0].trigger_kind == IK_CNS_TRIGGER_TIME_EQ);
    OK(wall[1].type == IK_CNS_CTRL_VEL_ADD);
    OK(wall[2].type == IK_CNS_CTRL_SCREEN_BOUND);
    OK(wall[2].trigger_kind == IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE_LT);
    OK(wall[2].trigger_value2 == 65);
    OK(wall[2].value0 == 1);
    OK(wall[2].value3 == 3);
    OK(wall[3].trigger_kind == IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE);
    OK(wall[3].trigger_value2 == 20);
    OK(wall[3].value0 == 1027);
    OK(wall[4].value0 == 5100);
    const ik_cns_state_t* zss1028 = ik_cns_find_state(&kfm_zss_cns, 1028);
    const ik_cns_controller_t* bounce =
        kfm_zss_cns.controllers + zss1028->controller_ofs;
    OK(bounce[1].type == IK_CNS_CTRL_VEL_SET);
    OK(bounce[2].trigger_kind == IK_CNS_TRIGGER_STATE_ENTRY_BACK_EDGE_LT);
    OK(bounce[3].type == IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS);
    OK(bounce[3].value0 == 5052 && bounce[3].value1 == 5050);
    OK(bounce[5].type == IK_CNS_CTRL_CHANGE_ANIM_DESCENT_IF_EXISTS);
    OK(bounce[5].value2 == 10 && bounce[5].value3 == 1);
    OK(bounce[6].value0 == 5100);
    const ik_cns_state_t* zss1027 = ik_cns_find_state(&kfm_zss_cns, 1027);
    const ik_cns_controller_t* impact =
        kfm_zss_cns.controllers + zss1027->controller_ofs;
    OK(impact[0].trigger_kind ==
       IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE);
    OK(impact[1].type == IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE);
    OK(impact[1].value0 == 15 * 256 && impact[1].value1 == 1);
    OK(impact[2].type == IK_CNS_CTRL_SCREEN_BACK_EFFECT);
    OK(impact[2].value0 == 72 && impact[2].value1 == -50);
    OK(impact[3].type == IK_CNS_CTRL_SOUND_EVENT);
    OK(impact[3].value0 == 7 && impact[3].value1 == 0);
    OK(impact[4].type == IK_CNS_CTRL_CHANGE_ANIM2);
    OK(impact[5].type == IK_CNS_CTRL_POS_FREEZE);
    OK(impact[6].type == IK_CNS_CTRL_SCREEN_BOUND);
    OK(impact[7].trigger_kind == IK_CNS_TRIGGER_ANIM_END);
    OK(impact[7].value0 == 1028);

    /* Exercise the *runtime predicate evaluator*, not only generated rows.
     * On recovery, near-ground wins over air recovery; negative vertical
     * velocity or unavailable recovery blocks both branches. */
    ik_cns_controller_context_t ctx{};
    ctx.alive = 1u;
    ctx.can_recover = 1u;
    ctx.vy_q8 = 256;
    ctx.command_mask = IK_CNS_COMMAND_RECOVERY;
    ctx.floor_y_q8 = 178 * 256;
    ctx.y_q8 = ctx.floor_y_q8 - 19 * 256;
    OK(ik_cns_controller_trigger_context_now(&airborne[1], &ctx));
    OK(ik_cns_controller_trigger_context_now(&airborne[2], &ctx));
    ctx.y_q8 = ctx.floor_y_q8 - 21 * 256;
    OK(!ik_cns_controller_trigger_context_now(&airborne[1], &ctx));
    OK(ik_cns_controller_trigger_context_now(&airborne[2], &ctx));
    ctx.can_recover = 0u;
    OK(!ik_cns_controller_trigger_context_now(&airborne[2], &ctx));
    ctx.can_recover = 1u;
    ctx.vy_q8 = -256;
    OK(!ik_cns_controller_trigger_context_now(&airborne[2], &ctx));
    ctx.vy_q8 = 256;
    ctx.command_mask = 0u;
    OK(!ik_cns_controller_trigger_context_now(&airborne[2], &ctx));

    /* 65-pixel screen lock is strict; 20-pixel wall hit is inclusive. */
    ctx.y_q8 = ctx.floor_y_q8 - 16 * 256;
    ctx.back_edge_body_dist_q8 = 64 * 256;
    ctx.front_edge_body_dist_q8 = 100 * 256;
    OK(ik_cns_controller_trigger_context_now(&wall[2], &ctx));
    OK(!ik_cns_controller_trigger_context_now(&wall[3], &ctx));
    ctx.back_edge_body_dist_q8 = 65 * 256;
    OK(!ik_cns_controller_trigger_context_now(&wall[2], &ctx));
    ctx.back_edge_body_dist_q8 = 20 * 256;
    OK(ik_cns_controller_trigger_context_now(&wall[3], &ctx));
    ctx.y_q8 = ctx.floor_y_q8 - 15 * 256;
    OK(!ik_cns_controller_trigger_context_now(&wall[3], &ctx));
    OK(kfm_zss_cns.constants.life == 1000);
    OK(ik_cns_find_state(&kfm_zss_cns, 200) != nullptr);

    bool saw_attack = false;
    bool saw_hurt = false;
    for (uint32_t i = 0; i < KFM_FRAME_COUNT; ++i) {
        saw_attack = saw_attack || kfm_frames[i].clsn1_count != 0u;
        saw_hurt = saw_hurt || kfm_frames[i].clsn2_count != 0u;
    }
    OK(saw_attack && saw_hurt);

    const ik_frame_table_t zss_table = {
        kfm_zss_frames, KFM_ZSS_FRAME_COUNT,
        kfm_zss_clsn_boxes, KFM_ZSS_CLSN_BOX_COUNT
    };
    const ik_frame_t* zss_frame = ik_frame_at_time(&zss_table, 0, 0u);
    OK(zss_frame != nullptr);
    OK(zss_frame->sprite_index < KFM_ZSS_SPRITE_COUNT);

    const ik_frame_table_t fx_table = {
        fightfx_frames, FIGHTFX_FRAME_COUNT,
        fightfx_clsn_boxes, FIGHTFX_CLSN_BOX_COUNT
    };
    const ik_frame_t* spark = ik_frame_at_time(&fx_table, 0, 0u);
    const ik_frame_t* guard = ik_frame_at_time(&fx_table, 40, 0u);
    OK(spark != nullptr && guard != nullptr);
    OK((spark->flags & IK_FRAME_FLAG_BLEND_ADD) != 0u);
    OK((guard->flags & IK_FRAME_FLAG_BLEND_ADD) != 0u);
    OK(fightfx_sprites[spark->sprite_index].palette_index < FIGHTFX_PALETTE_COUNT);

    /* The character uses more distinct sprites than LibSaturn has logical
     * texture slots (64), so the fight runtime must keep its bounded frame
     * texture cache instead of uploading everything. */
    OK(unique > 64u);

    const ik_frame_table_t table = {
        kfm_frames, KFM_FRAME_COUNT, kfm_clsn_boxes, KFM_CLSN_BOX_COUNT
    };
    static const int actions[] = {
        0,11,20,41,105,120,130,200,210,230,240,400,410,430,440
    };
    for (int action : actions) {
        for (uint32_t t = 0u; t < 40u; t += 7u) {
            const ik_frame_t* frame = ik_frame_at_time(&table, action, t);
            OK(frame != nullptr);
            int16_t dx = 0, dy = 0;
            ik_frame_screen_anchor(frame, 120, 178, -1, &dx, &dy);
        }
    }

    std::printf("[test] ikemen_assets OK (%lu unique sprites)\n",
                static_cast<unsigned long>(unique));
    return 0;
}
