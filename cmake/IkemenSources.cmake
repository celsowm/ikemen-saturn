# The runtime source lists, defined once.
#
# IKEMEN_LOGIC_SOURCES is the fight logic: pure C with no hardware access. The
# console firmware, the host unit tests and the oracle's Saturn-side trace
# binary all compile these same files, which is what makes the oracle
# comparison a statement about the code that runs on the console.
set(IKEMEN_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src")

file(GLOB IKEMEN_FIGHT_SOURCES CONFIGURE_DEPENDS "${IKEMEN_SRC_DIR}/ikemen_fight*.c")

set(IKEMEN_LOGIC_SOURCES
    ${IKEMEN_FIGHT_SOURCES}
    "${IKEMEN_SRC_DIR}/ikemen_frame.c"
    "${IKEMEN_SRC_DIR}/ikemen_anim.c"
    "${IKEMEN_SRC_DIR}/ikemen_cns.c"
    "${IKEMEN_SRC_DIR}/ikemen_command.c"
    "${IKEMEN_SRC_DIR}/ikemen_expr.c"
    "${IKEMEN_SRC_DIR}/ikemen_entity.c"
    "${IKEMEN_SRC_DIR}/ikemen_entity_runtime.c")

# Console-only code: the entry point, the disc asset store and the audio glue.
set(IKEMEN_FIRMWARE_SOURCES
    ${IKEMEN_LOGIC_SOURCES}
    "${IKEMEN_SRC_DIR}/main.c"
    "${IKEMEN_SRC_DIR}/ikemen_asset_store.c"
    "${IKEMEN_SRC_DIR}/ikemen_audio.c")
