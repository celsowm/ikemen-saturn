# Ikemen Saturn: Kung Fu Man vs ZSS Kung Fu Man on a Sega Saturn, behaving
# like upstream Ikemen GO frame by frame.
#
# This project provides the IkemenSaturn::IkemenSaturn CMake library target.
# Consumers link it and use libsaturn_configure_executable from LibSaturn.
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

project(IkemenSaturn VERSION ${IKEMEN_SATURN_VERSION} LANGUAGES C CXX)

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

# Install directories (GNU conventions, mirrored from LibSaturn)
set(IKEMEN_INSTALL_INCLUDEDIR include)
set(IKEMEN_INSTALL_LIBDIR lib)
set(IKEMEN_INSTALL_CMAKEDIR lib/cmake/IkemenSaturn)
set(IKEMEN_INSTALL_SHAREDIR share/ikemen_saturn)

# ---- Library target: ikemen_saturn -------------------------------------------
# Static library containing portable fight logic.
# Saturn platform sources (asset store, audio) are only added for Saturn builds.
if(CMAKE_SYSTEM_NAME STREQUAL "Generic")
    # Saturn (SH-2) build: include platform sources, link LibSaturn::Core PUBLIC
    add_library(ikemen_saturn_lib STATIC ${IKEMEN_LIBRARY_SOURCES})
    target_link_libraries(ikemen_saturn_lib PUBLIC LibSaturn::Core)
    target_compile_definitions(ikemen_saturn_lib PRIVATE IKEMEN_SATURN=1)
    target_compile_options(ikemen_saturn_lib
        PUBLIC
            -m2 -mb -ffreestanding -fomit-frame-pointer
            -ffunction-sections -fdata-sections
        PRIVATE
            -O2 -Wall -Wextra)
    # Generated headers (kfm_sounds.h, etc.) are needed by Saturn platform sources
    target_include_directories(ikemen_saturn_lib PRIVATE "${IKEMEN_GENERATED_ROOT}")
else()
    # Host (native) build: only portable core, no LibSaturn link (flags would propagate)
    # Manually add LibSaturn include directory for saturn/input.h needed by ikemen_command.h
    add_library(ikemen_saturn_lib STATIC ${IKEMEN_CORE_SOURCES})
    target_include_directories(ikemen_saturn_lib PRIVATE "${LibSaturn_INCLUDE_DIR}")
    target_compile_options(ikemen_saturn_lib
        PUBLIC
            -fPIC
        PRIVATE
            -O2 -Wall -Wextra)
endif()

add_library(IkemenSaturn::IkemenSaturn ALIAS ikemen_saturn_lib)

# The host machine may also have an installed IkemenSaturn header tree in
# LibSaturn's prefix. This target must compile against its own in-tree ABI.
target_include_directories(ikemen_saturn_lib BEFORE PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>")

set_target_properties(ikemen_saturn_lib PROPERTIES
    OUTPUT_NAME ikemen_saturn
    EXPORT_NAME IkemenSaturn
    C_STANDARD 11
    C_STANDARD_REQUIRED ON
    C_EXTENSIONS OFF
    POSITION_INDEPENDENT_CODE ON)

target_include_directories(ikemen_saturn_lib
    PUBLIC
        "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
        "$<INSTALL_INTERFACE:include>"
    PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}")

# Propagate LibSaturn dependency to consumers (for include directories and linking)
if(CMAKE_SYSTEM_NAME STREQUAL "Generic")
    # Saturn build: LibSaturn::Core is a static library target
    target_link_libraries(ikemen_saturn_lib INTERFACE LibSaturn::Core)
    # Ensure the dependency is exported for consumers
    set_target_properties(ikemen_saturn_lib PROPERTIES
        INTERFACE_LINK_LIBRARIES "LibSaturn::Core")
else()
    # Host build: LibSaturn::Core may not exist as a library; create interface dependency
    # Consumers will need to find_package(LibSaturn) separately
    target_link_libraries(ikemen_saturn_lib INTERFACE)
endif()

# Generated headers must exist before compiling the library
add_dependencies(ikemen_saturn_lib ikemen_assets)

# ---- Install rules ------------------------------------------------------------
install(TARGETS ikemen_saturn_lib
    EXPORT IkemenSaturnTargets
    ARCHIVE DESTINATION ${IKEMEN_INSTALL_LIBDIR}
    INCLUDES DESTINATION ${IKEMEN_INSTALL_INCLUDEDIR})

install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/include/ikemen_saturn"
    DESTINATION ${IKEMEN_INSTALL_INCLUDEDIR}
    FILES_MATCHING PATTERN "*.h")

# Install Python asset tools for consumers
install(FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_char_to_saturn.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cmd.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_zss_ai.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_common.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_controllers.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_emit.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_expr.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_parse.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_cns_state.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_text.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_oracle/ai_compare.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_sff/__main__.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_sff/emit.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_sff/stage.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/ikemen_sff/air.py"
    DESTINATION ${IKEMEN_INSTALL_SHAREDIR}/tools)

install(EXPORT IkemenSaturnTargets
    NAMESPACE IkemenSaturn::
    DESTINATION ${IKEMEN_INSTALL_CMAKEDIR})

# CMake package config
include(CMakePackageConfigHelpers)
set(IKEMEN_INSTALL_INCLUDEDIR_ABS "${CMAKE_INSTALL_PREFIX}/${IKEMEN_INSTALL_INCLUDEDIR}")

configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/IkemenSaturnConfig.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/IkemenSaturnConfig.cmake"
    INSTALL_DESTINATION ${IKEMEN_INSTALL_CMAKEDIR}
    PATH_VARS IKEMEN_INSTALL_INCLUDEDIR_ABS)

# Version compatibility: 0.x minor releases may break
if(PROJECT_VERSION_MAJOR EQUAL 0)
    set(_ikemen_compat SameMinorVersion)
else()
    set(_ikemen_compat SameMajorVersion)
endif()
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/IkemenSaturnConfigVersion.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY ${_ikemen_compat}
    ARCH_INDEPENDENT)

install(FILES
    "${CMAKE_CURRENT_BINARY_DIR}/IkemenSaturnConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/IkemenSaturnConfigVersion.cmake"
    DESTINATION ${IKEMEN_INSTALL_CMAKEDIR})

# Install helper functions for consumers
install(FILES
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/IkemenSaturnFunctions.cmake"
    DESTINATION ${IKEMEN_INSTALL_CMAKEDIR})

if(CMAKE_SYSTEM_NAME STREQUAL "Generic")
    # ---- Saturn firmware example application -----------------------------------
    add_executable(ikemen_saturn
        ${IKEMEN_FIRMWARE_SOURCES}
        ${IKEMEN_GENERATED_SOURCES})
    target_include_directories(ikemen_saturn PRIVATE
        "${IKEMEN_GENERATED_ROOT}")
    target_compile_options(ikemen_saturn PRIVATE -O2 -Wall -Wextra)

    option(IKEMEN_P2_IDLE "Hold P2 idle instead of enabling the native CPU" OFF)
    if(IKEMEN_P2_IDLE)
        target_compile_definitions(ikemen_saturn PRIVATE IKEMEN_P2_IDLE=1)
    endif()

    # Link the library (which brings LibSaturn::Core) and LibSaturn::Saturn for startup
    target_link_libraries(ikemen_saturn PRIVATE IkemenSaturn::IkemenSaturn LibSaturn::Saturn)

    libsaturn_configure_executable(ikemen_saturn)
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

# ---- Host: tests and the oracle's Saturn side ---------------------------------
include(CTest)

set(IKEMEN_HOST_FLAGS -Wall -Wextra -O1)
function(ikemen_host_target target)
    # The runtime sources are C but the unit tests are C++ and have always
    # compiled them as C++ with the project's tests; keep that.
    set_source_files_properties(${ARGN} PROPERTIES LANGUAGE CXX)
    target_compile_features(${target} PRIVATE cxx_std_20)
    target_compile_options(${target} PRIVATE ${IKEMEN_HOST_FLAGS})
    target_include_directories(${target} PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/include"
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
        "${IKEMEN_GENERATED_ROOT}"
        "${LibSaturn_INCLUDE_DIR}")
    # Link the library for host tests
    target_link_libraries(${target} PRIVATE IkemenSaturn::IkemenSaturn)
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
set(IKEMEN_TEST_SOURCES_test_ikemen_frame ${IKEMEN_LOGIC_SOURCES})
set(IKEMEN_TEST_SOURCES_test_ikemen_zss_ai
    ${IKEMEN_LOGIC_SOURCES}
    "${IKEMEN_GEN_DIR}/kfm_zss_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_frames.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_commands.c")
# Runtime contract against the actual generated KFM ZSS CNS/AIR assets:
# F72 screen-edge effect, system sound and post-Turn wall displacement.
set(IKEMEN_TEST_SOURCES_test_ikemen_zss_runtime
    ${IKEMEN_FIGHT_TEST_SOURCES}
    "${IKEMEN_GEN_DIR}/kfm_zss_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_frames.c")
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
    "${_ik}/ikemen_anim.c" "${_ik}/ikemen_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_frames.c" "${IKEMEN_GEN_DIR}/kfm_zss_frames.c"
    "${IKEMEN_GEN_DIR}/fightfx_frames.c" "${IKEMEN_GEN_DIR}/stage0_plane.c"
    "${IKEMEN_GEN_DIR}/kfm_cns.c" "${IKEMEN_GEN_DIR}/kfm_zss_cns.c")

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
    "${IKEMEN_GEN_DIR}/kfm_commands.c" "${IKEMEN_GEN_DIR}/kfm_state_rules.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_frames.c" "${IKEMEN_GEN_DIR}/kfm_zss_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_commands.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_state_rules.c")
ikemen_host_target(ikemen_oracle_trace ${IKEMEN_LOGIC_SOURCES}
    "${IKEMEN_GEN_DIR}/kfm_frames.c" "${IKEMEN_GEN_DIR}/kfm_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_commands.c" "${IKEMEN_GEN_DIR}/kfm_state_rules.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_frames.c" "${IKEMEN_GEN_DIR}/kfm_zss_cns.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_commands.c"
    "${IKEMEN_GEN_DIR}/kfm_zss_state_rules.c")
add_dependencies(ikemen_oracle_trace ikemen_assets)
set_target_properties(ikemen_oracle_trace PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

# Every ordinary CI push checks that the real mixed classic/ZSS character
# bundles can be replayed frame-by-frame (without Go/SDL dependencies).
add_test(NAME zss_trace_smoke
    COMMAND "${Python3_EXECUTABLE}" tools/ikemen_oracle/smoke_zss.py
            --trace-bin "$<TARGET_FILE:ikemen_oracle_trace>"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
set_tests_properties(zss_trace_smoke PROPERTIES LABELS "zss;oracle-host")

# AI has an independent opt-in smoke gate. It does not assert upstream
# decision parity (the original RNG and full AI.zss are not implemented).
add_test(NAME zss_native_ai_smoke
    COMMAND "${Python3_EXECUTABLE}" tools/ikemen_oracle/smoke_ai.py
            --trace-bin "$<TARGET_FILE:ikemen_oracle_trace>"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}")
set_tests_properties(zss_native_ai_smoke PROPERTIES LABELS "zss;cpu;oracle-host")

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
