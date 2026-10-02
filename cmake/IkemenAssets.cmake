# Generated asset ownership.
#
# The sprite, animation, command, state and sound tables and the packed sprite
# blobs that go on the disc are build outputs of the converters in tools/,
# produced from the pinned upstream data fetched by scripts/fetch_external.py
# (see NOTICE for the data's licenses). Nothing generated is committed.
#
#   IKEMEN_EXTERNAL_DIR   where the pinned upstream checkouts live
#                         (default: <source>/.external)
#
# Outputs, all under the build tree:
#   generated/ikemen_saturn/*.c|*.h      tables, included as "ikemen_saturn/x.h"
#   generated/ikemen_saturn/iso/*.BIN    sprite blobs, the disc's data root

set(IKEMEN_EXTERNAL_DIR "${CMAKE_CURRENT_SOURCE_DIR}/.external" CACHE PATH
    "Directory holding the pinned Ikemen-GO and Ikemen-GO-Screenpack checkouts")

set(IKEMEN_GENERATED_ROOT "${CMAKE_BINARY_DIR}/generated")
set(IKEMEN_GEN_DIR "${IKEMEN_GENERATED_ROOT}/ikemen_saturn")
set(IKEMEN_ISO_DIR "${IKEMEN_GEN_DIR}/iso")

set(_screenpack "${IKEMEN_EXTERNAL_DIR}/Ikemen-GO-Screenpack")
set(_ikemen_go "${IKEMEN_EXTERNAL_DIR}/Ikemen-GO")
set(KFM_SFF "${_screenpack}/chars/kfm/kfm.sff")
set(KFM_AIR "${_screenpack}/chars/kfm/kfm.air")
set(KFM_ZSS_SFF "${_screenpack}/chars/kfm_zss/kfm.sff")
set(KFM_ZSS_AIR "${_screenpack}/chars/kfm_zss/kfm.air")
set(KFM_SND "${_screenpack}/chars/kfm/kfm.snd")
set(KFM_CMD "${_screenpack}/chars/kfm/kfm.cmd")
set(KFM_CNS "${_screenpack}/chars/kfm/kfm.cns")
set(COMMON_CNS_ZSS "${_ikemen_go}/data/common1.cns.zss")
set(COMMON_SND "${_screenpack}/data/common.snd")
set(FIGHTFX_SFF "${_screenpack}/data/fightfx.sff")
set(FIGHTFX_AIR "${_screenpack}/data/fightfx.air")
set(STAGE0_SFF "${_screenpack}/stages/stage0.sff")

set(_inputs
    "${KFM_SFF}" "${KFM_AIR}" "${KFM_ZSS_SFF}" "${KFM_ZSS_AIR}" "${KFM_SND}"
    "${KFM_CMD}" "${KFM_CNS}" "${COMMON_CNS_ZSS}" "${COMMON_SND}"
    "${FIGHTFX_SFF}" "${FIGHTFX_AIR}" "${STAGE0_SFF}")
foreach(_input IN LISTS _inputs)
    if(NOT EXISTS "${_input}")
        message(FATAL_ERROR
            "Missing upstream data: ${_input}\n"
            "Run `python scripts/fetch_external.py` to fetch the pinned checkouts "
            "into ${IKEMEN_EXTERNAL_DIR}, or set -DIKEMEN_EXTERNAL_DIR=<dir>.")
    endif()
endforeach()

file(GLOB _sff_tool_sources CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_sff/*.py")
set(_tools "${CMAKE_CURRENT_SOURCE_DIR}/tools")

set(IKEMEN_FIGHTFX_ACTIONS "0,1,2,3,40,60,100,120")
set(IKEMEN_CHARACTER_ACTIONS "0,5,10,11,12,20,21,40,41,42,43,47,100,105,120,121,122,130,131,132,140,141,142,150,151,152,170,181,190,191,192,195,200,210,230,240,400,410,430,440,600,610,630,640,800,810,820,821,1000,1010,1020,1025,1027,1050,1051,1052,1055,1056,1060,1061,1070,1071,1100,1110,1120,1200,1210,1220,1300,1310,1320,1330,1340,1350,1351,1400,1410,1420,3000,3050,3051,5000,5001,5002,5005,5006,5007,5010,5011,5012,5015,5016,5017,5020,5021,5022,5025,5026,5027,5030,5035,5040,5050,5051,5061,5070,5080,5090,5100,5101,5160,5170,5110,5120,5140,5150,5200,5210")
set(IKEMEN_STATE_RULE_TARGETS "100,105,195,200,210,230,240,400,410,430,440,600,610,630,640,800,1000,1010,1020,1050,1060,1070,1100,1110,1120,1200,1210,1220,1300,1320,1340,1400,1410,1420,3000,3050")
set(IKEMEN_CNS_STATES "170,180,181,191,195,200,210,230,240,400,410,430,440,600,610,630,640,800,810,820,821,1000,1010,1020,1025,1026,1027,1028,1050,1051,1052,1055,1056,1060,1061,1070,1071,1075,1100,1110,1120,1200,1210,1220,1300,1310,1320,1330,1340,1350,1351,1400,1410,1420,3000,3050,3051")
set(IKEMEN_CNS_COMMON_STATES "0,10,11,12,20,40,45,50,51,52,100,105,106,120,130,131,132,140,150,151,152,153,154,155,5000,5001,5010,5011,5020,5030,5035,5040,5050,5070,5071,5080,5081,5100,5101,5110,5120,5150,5200,5201,5210")

file(MAKE_DIRECTORY "${IKEMEN_GEN_DIR}" "${IKEMEN_ISO_DIR}")

# A literal ";" inside an argument is written $<SEMICOLON> so the wrapper
# below does not split it as a CMake list.
# Every converter runs from the source root so `-m tools.ikemen_sff` resolves.
function(ikemen_generate)
    cmake_parse_arguments(G "" "COMMENT" "OUTPUTS;DEPENDS;COMMAND" ${ARGN})
    add_custom_command(
        OUTPUT ${G_OUTPUTS}
        COMMAND ${G_COMMAND}
        DEPENDS ${G_DEPENDS}
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        COMMENT "${G_COMMENT}"
        VERBATIM)
endfunction()

set(KFM_FRAMES_C "${IKEMEN_GEN_DIR}/kfm_frames.c")
set(KFM_SPRITES_BIN "${IKEMEN_ISO_DIR}/KFM_SPR.BIN")
ikemen_generate(COMMENT "Ikemen assets: KFM sprites and animations"
    OUTPUTS "${KFM_FRAMES_C}" "${IKEMEN_GEN_DIR}/kfm_frames.h" "${KFM_SPRITES_BIN}"
    DEPENDS "${KFM_SFF}" "${KFM_AIR}" ${_sff_tool_sources}
    COMMAND "${Python3_EXECUTABLE}" -m tools.ikemen_sff char
        --sff "${KFM_SFF}" --air "${KFM_AIR}"
        --actions "${IKEMEN_CHARACTER_ACTIONS}"
        --palettes "1,1$<SEMICOLON>1,4"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm" --symbol kfm
        --sprite-bin "${KFM_SPRITES_BIN}")

set(KFM_ZSS_FRAMES_C "${IKEMEN_GEN_DIR}/kfm_zss_frames.c")
set(KFM_ZSS_SPRITES_BIN "${IKEMEN_ISO_DIR}/KFM_ZSS.BIN")
ikemen_generate(COMMENT "Ikemen assets: ZSS Kung Fu Man sprites and animations"
    OUTPUTS "${KFM_ZSS_FRAMES_C}" "${IKEMEN_GEN_DIR}/kfm_zss_frames.h" "${KFM_ZSS_SPRITES_BIN}"
    DEPENDS "${KFM_ZSS_SFF}" "${KFM_ZSS_AIR}" ${_sff_tool_sources}
    COMMAND "${Python3_EXECUTABLE}" -m tools.ikemen_sff char
        --sff "${KFM_ZSS_SFF}" --air "${KFM_ZSS_AIR}"
        --actions "${IKEMEN_CHARACTER_ACTIONS}"
        --palettes "1,1"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm_zss" --symbol kfm_zss
        --sprite-bin "${KFM_ZSS_SPRITES_BIN}")

set(FIGHTFX_FRAMES_C "${IKEMEN_GEN_DIR}/fightfx_frames.c")
set(FIGHTFX_SPRITES_BIN "${IKEMEN_ISO_DIR}/FIGHTFX.BIN")
ikemen_generate(COMMENT "Ikemen assets: fight effects"
    OUTPUTS "${FIGHTFX_FRAMES_C}" "${IKEMEN_GEN_DIR}/fightfx_frames.h" "${FIGHTFX_SPRITES_BIN}"
    DEPENDS "${FIGHTFX_SFF}" "${FIGHTFX_AIR}" ${_sff_tool_sources}
    COMMAND "${Python3_EXECUTABLE}" -m tools.ikemen_sff fx
        --sff "${FIGHTFX_SFF}" --air "${FIGHTFX_AIR}"
        --actions "${IKEMEN_FIGHTFX_ACTIONS}"
        --out-prefix "${IKEMEN_GEN_DIR}/fightfx" --symbol fightfx
        --sprite-bin "${FIGHTFX_SPRITES_BIN}")

set(STAGE0_PLANE_C "${IKEMEN_GEN_DIR}/stage0_plane.c")
ikemen_generate(COMMENT "Ikemen assets: stage 0 background plane"
    OUTPUTS "${STAGE0_PLANE_C}" "${IKEMEN_GEN_DIR}/stage0_plane.h"
    DEPENDS "${STAGE0_SFF}" ${_sff_tool_sources}
    COMMAND "${Python3_EXECUTABLE}" -m tools.ikemen_sff stage
        --sff "${STAGE0_SFF}"
        --layers "0,0:start=0,0:tile$<SEMICOLON>0,1:start=0,185:tile"
        --out-prefix "${IKEMEN_GEN_DIR}/stage0" --symbol stage0)

set(KFM_SOUNDS_C "${IKEMEN_GEN_DIR}/kfm_sounds.c")
ikemen_generate(COMMENT "Ikemen assets: sounds"
    OUTPUTS "${KFM_SOUNDS_C}" "${IKEMEN_GEN_DIR}/kfm_sounds.h"
    DEPENDS "${KFM_SND}" "${COMMON_SND}" "${_tools}/ikemen_snd.py"
    COMMAND "${Python3_EXECUTABLE}" "${_tools}/ikemen_snd.py"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm_sounds" --symbol kfm_sounds
        --sound punch_whiff "${KFM_SND}" 0 0
        --sound kick_whiff "${KFM_SND}" 0 1
        --sound strong_punch_whiff "${KFM_SND}" 0 4
        --sound sweep_whiff "${KFM_SND}" 0 2
        --sound special_whiff "${KFM_SND}" 0 3
        --sound throw_voice "${KFM_SND}" 1 1
        --sound throw_slam "${KFM_SND}" 800 0
        --sound landing "${KFM_SND}" 40 0
        --sound knee_voice "${KFM_SND}" 100 0
        --sound super_pause "${COMMON_SND}" 20 0
        --sound punch_hit "${COMMON_SND}" 5 0
        --sound kick_hit "${COMMON_SND}" 5 1
        --sound strong_hit "${COMMON_SND}" 5 2
        --sound air_strong_hit "${COMMON_SND}" 5 3
        --sound heavy_hit "${COMMON_SND}" 5 4
        --sound reversal_hit "${COMMON_SND}" 6 0)

set(KFM_COMMANDS_C "${IKEMEN_GEN_DIR}/kfm_commands.c")
ikemen_generate(COMMENT "Ikemen assets: command table"
    OUTPUTS "${KFM_COMMANDS_C}" "${IKEMEN_GEN_DIR}/kfm_commands.h"
    DEPENDS "${KFM_CMD}" "${_tools}/ikemen_cmd.py"
    COMMAND "${Python3_EXECUTABLE}" "${_tools}/ikemen_cmd.py"
        --cmd "${KFM_CMD}"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm_commands" --symbol kfm)

set(KFM_STATE_RULES_C "${IKEMEN_GEN_DIR}/kfm_state_rules.c")
ikemen_generate(COMMENT "Ikemen assets: state transition rules"
    OUTPUTS "${KFM_STATE_RULES_C}" "${IKEMEN_GEN_DIR}/kfm_state_rules.h"
    DEPENDS "${KFM_CMD}" "${_tools}/ikemen_state_rules.py" "${_tools}/ikemen_cmd.py"
    COMMAND "${Python3_EXECUTABLE}" -m tools.ikemen_state_rules
        --cmd "${KFM_CMD}"
        --targets "${IKEMEN_STATE_RULE_TARGETS}"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm_state_rules" --symbol kfm)

set(KFM_CNS_C "${IKEMEN_GEN_DIR}/kfm_cns.c")
ikemen_generate(COMMENT "Ikemen assets: state controllers"
    OUTPUTS "${KFM_CNS_C}" "${IKEMEN_GEN_DIR}/kfm_cns.h"
    DEPENDS "${KFM_CNS}" "${KFM_AIR}" "${COMMON_CNS_ZSS}" "${_tools}/ikemen_cns.py"
    COMMAND "${Python3_EXECUTABLE}" "${_tools}/ikemen_cns.py"
        --cns "${KFM_CNS}" --air "${KFM_AIR}"
        --states "${IKEMEN_CNS_STATES}"
        --common-zss "${COMMON_CNS_ZSS}"
        --common-states "${IKEMEN_CNS_COMMON_STATES}"
        --out-prefix "${IKEMEN_GEN_DIR}/kfm_cns" --symbol kfm)

set(IKEMEN_GENERATED_SOURCES
    "${KFM_FRAMES_C}" "${KFM_ZSS_FRAMES_C}" "${FIGHTFX_FRAMES_C}" "${STAGE0_PLANE_C}"
    "${KFM_SOUNDS_C}" "${KFM_COMMANDS_C}" "${KFM_STATE_RULES_C}" "${KFM_CNS_C}")
set(IKEMEN_ISO_FILES "${KFM_SPRITES_BIN}" "${KFM_ZSS_SPRITES_BIN}" "${FIGHTFX_SPRITES_BIN}")

# One target that owns every generated file, so the host tests and the
# firmware agree on a single generation step per build tree.
add_custom_target(ikemen_assets DEPENDS ${IKEMEN_GENERATED_SOURCES} ${IKEMEN_ISO_FILES})
