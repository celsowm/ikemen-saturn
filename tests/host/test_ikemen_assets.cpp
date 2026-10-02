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
