#ifndef IKEMEN_SATURN_VERSION_H
#define IKEMEN_SATURN_VERSION_H

#define IKEMEN_SATURN_VERSION "0.1.0"
#define IKEMEN_SATURN_VERSION_MAJOR 0
#define IKEMEN_SATURN_VERSION_MINOR 1
#define IKEMEN_SATURN_VERSION_PATCH 0

/* Feature guard for Saturn-specific APIs (ikemen_audio.h, ikemen_asset_store.h).
 * Defined when building for the Sega Saturn target. */
#ifndef IKEMEN_SATURN
#  if defined(__sh__) || defined(__SH2__) || defined(SATURN)
#    define IKEMEN_SATURN 1
#  else
#    define IKEMEN_SATURN 0
#  endif
#endif

#endif /* IKEMEN_SATURN_VERSION_H */