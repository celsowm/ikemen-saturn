# The runtime source lists, defined once.
#
# IKEMEN_CORE_SOURCES is the portable fight logic: pure C with no hardware access.
# The console firmware, the host unit tests and the oracle's Saturn-side trace
# binary all compile these same files, which is what makes the oracle
# comparison a statement about the code that runs on the console.
#
# IKEMEN_SATURN_SOURCES are the Saturn platform glue (asset store, audio).
#
# IKEMEN_FIRMWARE_SOURCES is the example application: main.c + Saturn sources.
set(IKEMEN_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")

file(GLOB IKEMEN_FIGHT_SOURCES CONFIGURE_DEPENDS "${IKEMEN_SRC_DIR}/ikemen_fight*.c")

# Portable core: all fight logic, no hardware dependencies
set(IKEMEN_CORE_SOURCES
    ${IKEMEN_FIGHT_SOURCES}
    "${IKEMEN_SRC_DIR}/ikemen_frame.c"
    "${IKEMEN_SRC_DIR}/ikemen_zss_ai.c"
    "${IKEMEN_SRC_DIR}/ikemen_anim.c"
    "${IKEMEN_SRC_DIR}/ikemen_cns.c"
    "${IKEMEN_SRC_DIR}/ikemen_command.c"
    "${IKEMEN_SRC_DIR}/ikemen_expr.c"
    "${IKEMEN_SRC_DIR}/ikemen_entity.c"
    "${IKEMEN_SRC_DIR}/ikemen_entity_runtime.c")

# Saturn platform: CD/ramcart asset loading, SCSP audio glue
set(IKEMEN_SATURN_SOURCES
    "${IKEMEN_SRC_DIR}/ikemen_asset_store.c"
    "${IKEMEN_SRC_DIR}/ikemen_audio.c")

# Library target: core + Saturn platform
set(IKEMEN_LIBRARY_SOURCES
    ${IKEMEN_CORE_SOURCES}
    ${IKEMEN_SATURN_SOURCES})

# Console-only example application: the entry point
set(IKEMEN_FIRMWARE_SOURCES
    ${IKEMEN_LIBRARY_SOURCES}
    "${IKEMEN_SRC_DIR}/main.c")

# For host tests: the logic sources (same as core)
set(IKEMEN_LOGIC_SOURCES ${IKEMEN_CORE_SOURCES})