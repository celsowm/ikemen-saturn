# Executable helpers shipped with the IkemenSaturn package.
#
# Installed to <prefix>/lib/cmake/IkemenSaturn and loaded by
# IkemenSaturnConfig.cmake, so consumers never need to know physical paths.

include_guard(GLOBAL)

# ikemen_saturn_configure_executable(<target>
#     [MAP_FILE <path>]      default: <target file>.map
#     [NO_CTOR_CHECK])       skip the post-link .init_array validation
#
# Owns the Saturn application link contract for Ikemen games: links
# IkemenSaturn::IkemenSaturn + LibSaturn::Saturn, sets SH-2 machine flags,
# -nostdlib, the LibSaturn linker script, section garbage collection, a link
# map, and the guard that rejects executables whose static constructors crt0
# would never run.
function(ikemen_saturn_configure_executable target)
    cmake_parse_arguments(PARSE_ARGV 1 ARG "NO_CTOR_CHECK" "MAP_FILE" "")
    if(ARG_UNPARSED_ARGUMENTS)
        message(FATAL_ERROR
            "ikemen_saturn_configure_executable: unknown arguments ${ARG_UNPARSED_ARGUMENTS}")
    endif()
    if(NOT TARGET ${target})
        message(FATAL_ERROR "ikemen_saturn_configure_executable: '${target}' is not a target")
    endif()

    # Find LibSaturn's linker script and check scripts
    find_package(LibSaturn CONFIG REQUIRED)
    if(NOT LIBSATURN_LINKER_SCRIPT OR NOT EXISTS "${LIBSATURN_LINKER_SCRIPT}")
        message(FATAL_ERROR
            "ikemen_saturn_configure_executable: LibSaturn linker script '${LIBSATURN_LINKER_SCRIPT}' not found")
    endif()
    if(NOT LIBSATURN_CMAKE_SCRIPT_DIR OR NOT IS_DIRECTORY "${LIBSATURN_CMAKE_SCRIPT_DIR}")
        message(FATAL_ERROR
            "ikemen_saturn_configure_executable: LibSaturn CMake script dir '${LIBSATURN_CMAKE_SCRIPT_DIR}' not found")
    endif()

    # Link IkemenSaturn + LibSaturn::Saturn (which includes LibSaturn::Core + Startup)
    target_link_libraries(${target} PRIVATE IkemenSaturn::IkemenSaturn LibSaturn::Saturn)

    set(_map "${ARG_MAP_FILE}")
    if(NOT _map)
        set(_map "$<TARGET_FILE:${target}>.map")
    endif()
    target_link_options(${target} PRIVATE
        -m2 -mb -nostdlib
        "-Wl,-T,${LIBSATURN_LINKER_SCRIPT}"
        "-Wl,-Map,${_map}"
        -Wl,--gc-sections)
    set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS "${LIBSATURN_LINKER_SCRIPT}")
    set_property(TARGET ${target} PROPERTY SUFFIX ".elf")

    if(NOT ARG_NO_CTOR_CHECK)
        if(NOT CMAKE_OBJDUMP)
            message(FATAL_ERROR
                "ikemen_saturn_configure_executable: CMAKE_OBJDUMP is not set; use the "
                "sh2eb-elf toolchain file or pass NO_CTOR_CHECK")
        endif()
        # crt0 never runs static constructors, so a global that needs one is
        # silently left null. Fail the link instead of shipping that.
        add_custom_command(TARGET ${target} POST_BUILD
            COMMAND "${CMAKE_COMMAND}"
                    "-DELF=$<TARGET_FILE:${target}>"
                    "-DOBJDUMP=${CMAKE_OBJDUMP}"
                    -P "${LIBSATURN_CMAKE_SCRIPT_DIR}/LibSaturnCheckNoInitArray.cmake"
            COMMENT "Checking ${target} for static constructors"
            VERBATIM)
    endif()
endfunction()

# Convenience wrapper: create disc image using LibSaturn's helper.
# Just forwards to libsaturn_add_disc after ensuring LibSaturn is found.
function(ikemen_saturn_add_disc target)
    find_package(LibSaturn CONFIG REQUIRED)
    # Forward all arguments to libsaturn_add_disc
    libsaturn_add_disc(${target} ${ARGN})
endfunction()