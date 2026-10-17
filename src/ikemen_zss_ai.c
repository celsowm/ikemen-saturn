#include "ikemen_zss_ai.h"
/* AI.zss State -1: knee follow-up, verbatim condition from lines 429-434.
 * Source drift is rejected by the KFM ZSS asset compiler.
 */
int ik_zss_ai_request(const ik_fight_t* fight, uint8_t player,
                      uint8_t level, int16_t* destination) {
    if (!fight || !destination || player >= 2u || level < 1u ||
        level > 8u || fight->round_state != 2u) return 0;
    const ik_fighter_t* f = &fight->fighters[player];
    if ((f->state != 1051 && f->state != 1061 && f->state != 1071) ||
        f->vy_q8 >= -IK_CNS_Q8_ONE ||
        (!f->move_hit && !(f->move_contact && level < 6u))) return 0;
    *destination = f->state == 1071 ? 1075 : 1055;
    return 1;
}
