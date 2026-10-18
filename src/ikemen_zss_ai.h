#ifndef IKEMEN_ZSS_AI_H
#define IKEMEN_ZSS_AI_H
/* Source-guarded KFM ZSS CPU slice; no upstream RNG or full-AI parity. */
#include <stdint.h>
#include "ikemen_fight.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Return 1 and set destination when an original CPU State -1 branch fires.
 * Other branches (including random neutral choices) are not implemented. */
int ik_zss_ai_request(const ik_fight_t* fight, uint8_t player,
                      uint8_t level, int16_t* destination);
/* Native neutral/defense/combo CPU. Seeded RNG is not upstream-compatible. */
int ik_zss_ai_tick(const ik_fight_t* fight, uint8_t player,
                   uint8_t level, uint32_t* rng, ik_fight_controls_t* out);
#ifdef __cplusplus
}
#endif
#endif
