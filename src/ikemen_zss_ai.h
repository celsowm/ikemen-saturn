#ifndef IKEMEN_ZSS_AI_H
#define IKEMEN_ZSS_AI_H
/* Source-guarded KFM ZSS CPU slice; original RNG function but NOT
 * global RNG consumption order or full AI decision parity. */
#include <stdint.h>
#include "ikemen_fight.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Return 1 and set destination when an original CPU State -1 branch fires.
 * Other branches (including random neutral choices) are not implemented. */
int ik_zss_ai_request(const ik_fight_t* fight, uint8_t player,
                      uint8_t level, int16_t* destination);
/* Original pinned Go Park-Miller Random() and OC_random (0..999) for
 * seeded isolated streams. Does not reproduce the engine's call order.
 * state stores the full bit pattern of an Ikemen int32 random seed. */
int32_t ik_zss_ai_rng_next(uint32_t* state);
int32_t ik_zss_ai_random_trigger(uint32_t* state);
/* Native neutral/defense/combo CPU with original random distribution. */
int ik_zss_ai_tick(const ik_fight_t* fight, uint8_t player,
                   uint8_t level, uint32_t* rng, ik_fight_controls_t* out);
#ifdef __cplusplus
}
#endif
#endif
