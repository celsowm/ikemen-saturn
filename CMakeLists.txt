# Ikemen Saturn: Kung Fu Man vs ZSS Kung Fu Man on a Sega Saturn, behaving
# like upstream Ikemen GO frame by frame.
#
# This project is an ordinary external consumer of an installed LibSaturn
# package. It reaches the library only through
#
#     find_package(LibSaturn CONFIG REQUIRED)     ->  LibSaturn::Saturn
#
# and the helpers that package ships (libsaturn_configure_executable,
# libsaturn_add_binary, libsaturn_add_disc). There is no sibling checkout, no
# add_subdirectory(), no private header and no library build-tree path.
#
# Two configurations, chosen by the toolchain:
#   saturn  the SH-2 toolchain file from the LibSaturn prefix: firmware ELF,
#           0.BIN and a bootable disc (cmake --preset saturn)
#   host    the native compiler: unit tests, the Saturn-side oracle trace
#           binary and the Python tool tests (cmake --preset host)
cmake_minimum_required(VERSION 3.24)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" IKEMEN_SATURN_VERSION LIMIT_COUNT 1)
string(STRIP "${IKEMEN_SATURN_VERSION}" IKEMEN_SATURN_VERSION)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION")

project(ikemen_saturn VERSION ${IKEMEN_SATURN_VERSION} LANGUAGES C CXX)

set(LIBSATURN_MIN_VERSION 0.1)
option(IKEMEN_ENABLE_ORACLE_TESTS
    "Register the upstream Ikemen GO oracle suite with ctest (needs Go, SDL2, ffmpeg, libxmp)" OFF)

# The package is found the same way for both configurations: the host build
# only needs its public headers (saturn/input.h), the firmware build links it.
find_package(LibSaturn ${LIBSATURN_MIN_VERSION} CONFIG REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# The sprite converters decode PNGs with Pillow; fail here, with the fix, rather
# than deep inside the asset build.
execute_process(COMMAND "${Python3_EXECUTABLE}" -c "import PIL"
    RESULT_VARIABLE _pillow_rc OUTPUT_QUIET ERROR_QUIET)
if(NOT _pillow_rc EQUAL 0)
    message(FATAL_ERROR
        "Pillow is not installed for ${Python3_EXECUTABLE} (needed by the sprite "
        "converters). Run: \"${Python3_EXECUTABLE}\" -m pip install -r "
        "${CMAKE_CURRENT_SOURCE_DIR}/requirements.txt")
endif()

include(cmake/IkemenSources.cmake)
include(cmake/IkemenAssets.cmake)

if(CMAKE_SYSTEM_NAME STREQUAL "Generic")
    # ---- firmware -------------------------------------------------------
    add_executable(ikemen_saturn
        ${IKEMEN_FIRMWARE_SOURCES}
        ${IKEMEN_GENERATED_SOURCES})
    target_include_directories(ikemen_saturn PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${IKEMEN_GENERATED_ROOT}")
    # The runtime is tuned for -O2 (it matches the library and the original
    # Makefile build); -O2 comes last so it wins over any config default.
    target_compile_options(ikemen_saturn PRIVATE -O2 -Wall -Wextra)
    target_link_libraries(ikemen_saturn PRIVATE LibSaturn::Saturn)
    libsaturn_configure_executable(ikemen_saturn)
    # 0.BIN limit of the Saturn application load area.
    libsaturn_add_binary(ikemen_saturn MAX_BYTES 983040)
    libsaturn_add_disc(ikemen_saturn
        NAME ikemen_saturn
        ROOT_DIRS "${IKEMEN_ISO_DIR}"
        DEPENDS ${IKEMEN_ISO_FILES}
        ALL)
    install(FILES
            "$<TARGET_FILE:ikemen_saturn>"
            "$<TARGET_FILE_DIR:ikemen_saturn>/ikemen_saturn.app.bin"
        DESTINATION bin)
    return()
endif()

# ---- host: tests and the oracle's Saturn side -----------------------------
include(CTest)

set(IKEMEN_HOST_FLAGS -Wall -Wextra -O1)
function(ikemen_host_target target)
    # The runtime sources are C but the unit tests are C++ and have always
    # compiled them as C++ with the project's tests; keep that.
    set_source_files_properties(${ARGN} PROPERTIES LANGUAGE CXX)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_options(${target} PRIVATE ${IKEMEN_HOST_FLAGS})
    target_include_directories(${target} PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${IKEMEN_GENERATED_ROOT}"
        "${LibSaturn_INCLUDE_DIR}")
endfunction()

# Which runtime sources each unit test exercises (the logic lives in .c files
# and the tests stub nothing, so they link exactly what they test).
set(_ik "${CMAKE_CURRENT_SOURCE_DIR}/src")
set(IKEMEN_FIGHT_TEST_SOURCES
    ${IKEMEN_FIGHT_SOURCES}
    "${_ik}/ikemen_anim.c" "${_ik}/ikemen_cns.c"
    "${_ik}/ikemen_entity.c" "${_ik}/ikemen_entity_runtime.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_fight ${IKEMEN_FIGHT_TEST_SOURCES})
set(IKEMEN_TEST_SOURCES_test_ikemen_command "${_ik}/ikemen_command.c" "${_ik}/ikemen_expr.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_expr "${_ik}/ikemen_expr.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_entity "${_ik}/ikemen_entity.c" "${_ik}/ikemen_expr.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_entity_runtime
    "${_ik}/ikemen_entity.c" "${_ik}/ikemen_entity_runtime.c"
    "${_ik}/ikemen_cns.c" "${_ik}/ikemen_anim.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_helper_combat
    ${IKEMEN_FIGHT_SOURCES}
    "${_ik}/ikemen_entity.c" "${_ik}/ikemen_entity_runtime.c"
    "${_ik}/ikemen_cns.c" "${_ik}/ikemen_anim.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_cns "${_ik}/ikemen_cns.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_anim "${_ik}/ikemen_anim.c")
set(IKEMEN_TEST_SOURCES_test_ikemen_decode "${_ik}/ikemen_anim.c")
# End-to-end asset contract: needs the generated tables and sprite blobs.
set(IKEMEN_TEST_SOURCES_test_ikemen_assets
    "${_ik}/ikemen_anim.c"
    "${IKEMEN_GEN_DIR}/kfm_frames.c" "${IKEMEN_GEN_DIR}/kfm_zss_frames.c"
    "${IKEMEN_GEN_DIR}/fightfx_frames.c" "${IKEMEN_GEN_DIR}/stage0_plane.c")

file(GLOB IKEMEN_HOST_TESTS CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/host/*.cpp")
foreach(_test_src IN LISTS IKEMEN_HOST_TESTS)
    get_filename_component(_name "${_test_src}" NAME_WE)
    if(NOT DEFINED IKEMEN_TEST_SOURCES_${_name})
        message(FATAL_ERROR "host test ${_name} has no source list: add IKEMEN_TEST_SOURCES_${_name}")
    endif()
    add_executable(${_name} "${_test_src}" ${IKEMEN_TEST_SOURCES_${_name}})
    ikemen_host_target(${_name} ${IKEMEN_TEST_SOURCES_${_name}})
    add_dependencies(${_name} ikemen_assets)
    set_target_properties(${_name} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/tests")
    add_test(NAME ${_name} COMMAND ${_name} WORKING_DIRECTORY "${CMAKE_BINARY_DIR}")
endforeach()
# The asset test reads the generated sprite blobs from the build tree.
set_property(TEST test_ikemen_assets PROPERTY ENVIRONMENT
    "IKEMEN_ISO_DIR=${IKEMEN_ISO_DIR}")

# The Saturn side of the oracle: the exact logic the console runs (one source
# list, IKEMEN_LOGIC_SOURCES) driven by the same ik_frame_step() as main.c.
add_executable(ikemen_oracle_trace
    tools/ikemen_oracle/saturn_trace.cpp
    ${IKEMEN_LOGIC_SOURCES}
    "${IKEMEN_GEN_DIR}/kfm_frames.c" "${IKEMEN_GEN_DIR}/kfm_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_commands.c" "${IKEMEN_GEN_DIR}/kfm_state_rules.c")
ikemen_host_target(ikemen_oracle_trace ${IKEMEN_LOGIC_SOURCES}
    "${IKEMEN_GEN_DIR}/kfm_frames.c" "${IKEMEN_GEN_DIR}/kfm_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_commands.c" "${IKEMEN_GEN_DIR}/kfm_state_rules.c")
add_dependencies(ikemen_oracle_trace ikemen_assets)
set_target_properties(ikemen_oracle_trace PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

# Python tool tests: scripts that exit non-zero on failure.
file(GLOB IKEMEN_TOOL_TESTS CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/tests/tools/test_*.py")
foreach(_test_src IN LISTS IKEMEN_TOOL_TESTS)
    get_filename_component(_name "${_test_src}" NAME_WE)
    add_test(NAME py_${_name}
        COMMAND "${Python3_EXECUTABLE}" "${_test_src}"
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
    set_property(TEST py_${_name} PROPERTY ENVIRONMENT
        "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}")
endforeach()

# Behavioral oracle: upstream Ikemen GO vs the host build, frame by frame.
add_custom_target(ikemen_oracle_suite
    COMMAND "${Python3_EXECUTABLE}" tools/ikemen_oracle/suite.py
            --trace-bin "$<TARGET_FILE:ikemen_oracle_trace>" --keep-going
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    DEPENDS ikemen_oracle_trace
    USES_TERMINAL
    COMMENT "Running the Ikemen GO oracle suite")
if(IKEMEN_ENABLE_ORACLE_TESTS)
    add_test(NAME oracle_suite
        COMMAND "${Python3_EXECUTABLE}" tools/ikemen_oracle/suite.py
                --trace-bin "$<TARGET_FILE:ikemen_oracle_trace>" --keep-going
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
    set_tests_properties(oracle_suite PROPERTIES TIMEOUT 7200 LABELS oracle)
endif()
