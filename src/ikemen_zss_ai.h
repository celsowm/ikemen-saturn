#ifndef IKEMEN_ZSS_AI_H
#define IKEMEN_ZSS_AI_H
/* Deterministic, source-checked subset of original KFM ZSS AI.zss. */
#include <stdint.h>
#include "ikemen_fight.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Return 1 and set destination when an original CPU State -1 branch fires.
 * Other branches (including random neutral choices) are not implemented. */
int ik_zss_ai_request(const ik_fight_t* fight, uint8_t player,
                      uint8_t level, int16_t* destination);
#ifdef __cplusplus
}
#endif
#endif
