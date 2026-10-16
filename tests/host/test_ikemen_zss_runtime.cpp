#include <cstdio>
#include <cstdlib>

#include "ikemen_fight_internal.h"
#include "ikemen_saturn/kfm_zss_cns.h"
#include "ikemen_saturn/kfm_zss_frames.h"

#define OK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); std::exit(1); } } while (0)

static const ik_frame_table_t zss_frames = {
    kfm_zss_frames, KFM_ZSS_FRAME_COUNT,
    kfm_zss_clsn_boxes, KFM_ZSS_CLSN_BOX_COUNT
};

static void initialize(ik_fight_t* fight, int x, int facing) {
    ik_fight_init_players(fight, &kfm_zss_cns, &kfm_zss_cns);
    fight->player_frames[0] = &zss_frames;
    fight->player_frames[1] = &zss_frames;

    /* Camera window 160..480; character is near the right/left edge of
     * the stage, independent of the visible camera boundaries. */
    fight->cam_x_q16 = 320 * 65536;
    fight->cam_half_q16 = 160 * 65536;
    ik_fighter_t* f = &fight->fighters[0];
    f->state = 1027;
    f->state_owner = 0u;
    f->anim_owner = 0u;
    f->anim = 1027;
    f->anim_time = 0u;
    f->state_time = 0u;
    f->cur_state_type = IK_CNS_STATE_AIR;
    f->cur_move_type = IK_CNS_MOVE_HIT;
    f->on_ground = 0u;
    f->facing = (int8_t)facing;
    f->xmin_q8 = 0;
    f->xmax_q8 = 640 * 256;
    f->x_q8 = x * 256;
    f->y_q8 = 178 * 256;
    f->x = (int16_t)x;
    f->y = 178;
    f->edge_back = 12;
    f->edge_front = 12;
}

int main() {
    const ik_cns_state_t* source = ik_cns_find_state(&kfm_zss_cns, 1027);
    OK(source && source->controller_count == 8u);
    OK(ik_frames_bounds(&zss_frames, 1027, nullptr, nullptr));
    ik_fight_controls_t idle{};

    {
        static ik_fight_t fight;
        initialize(&fight, 610, 1);
        ik_fighter_t* f = &fight.fighters[0];
        OK(ikf_process_cns_controllers(
            &fight, f, &idle, &zss_frames, 0) == 0);
        /* Front gap 17.5px (air size offset) triggers turn. New BACK gap
         * must be measured after turning: 30-12-0.5 = 17.5px, producing
         * a +2.5px displacement against the new facing. */
        OK(f->facing == -1);
        OK(f->x_q8 == (610 * 256 + 128));
        OK(f->pos_freeze_x && f->pos_freeze_y);
        OK(f->screen_bound == 1u);
        OK(f->move_camera_x == 0u && f->move_camera_y == 1u);
        OK(fight.effect_count == 1u);
        OK(fight.effect_events[0].action == 72);
        OK(fight.effect_events[0].x == 480);
        OK(fight.effect_events[0].y == 128);
        OK(fight.sound_count == 1u);
        OK(fight.sound_events[0].group == 7);
        OK(fight.sound_events[0].item == 0);
        OK(f->anim == 1027);
    }
    {
        static ik_fight_t fight;
        initialize(&fight, 320, 1);
        ik_fighter_t* f = &fight.fighters[0];
        OK(ikf_process_cns_controllers(
            &fight, f, &idle, &zss_frames, 0) == 0);
        OK(f->facing == 1);
        OK(fight.effect_count == 1u);
        OK(fight.effect_events[0].action == 72);
        OK(fight.effect_events[0].x == 160);
        OK(fight.effect_events[0].y == 128);
        OK(fight.sound_count == 1u);
        /* No front-edge turn: back distance is 320-12-.5=307.5px. */
        OK(f->x_q8 == 320 * 256 + (15 * 256 - (307 * 256 + 128)));
    }
    std::puts("[test] native ZSS 1027 screen edge F72 / SysSnd OK");
    return 0;
}
