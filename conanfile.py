"""Conan 2 recipe for Ikemen Saturn.

An ordinary LibSaturn consumer: `requires("libsaturn")` and nothing else. The
recipe configures the project's own CMakeLists.txt with the Saturn host
profile; CMakeToolchain puts the libsaturn package folder on CMAKE_PREFIX_PATH
and the project's unmodified `find_package(LibSaturn CONFIG REQUIRED)` resolves
the installed config, exactly as it does for a `cmake --install` prefix.

    conan config install <libsaturn>/packaging/conan/config   # saturn-sh2eb profile
    conan create <libsaturn> --profile:host=saturn-sh2eb --profile:build=default
    conan create . --profile:host=saturn-sh2eb --profile:build=default

The game data (upstream Ikemen GO assets) is fetched at build time from the
pins in scripts/external-pins.env; none of it is stored in the package sources.

The sprite converters need Pillow in the Python that runs Conan:

    python -m pip install -r requirements.txt
"""
import os
import subprocess
import sys

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout
from conan.tools.files import copy, load


class IkemenSaturnConan(ConanFile):
    name = "ikemen-saturn"
    description = "Ikemen GO behavior on a Sega Saturn, validated against upstream frame by frame"
    license = "MIT"
    url = "https://github.com/celsowm/ikemen-saturn"
    homepage = "https://github.com/celsowm/ikemen-saturn"
    topics = ("sega-saturn", "ikemen-go", "mugen", "fighting-game")

    package_type = "application"
    settings = "os", "arch", "compiler", "build_type"

    exports_sources = (
        "CMakeLists.txt", "VERSION", "LICENSE", "NOTICE.md",
        "cmake/*", "src/*", "tools/*", "scripts/external-pins.env",
        "scripts/fetch_external.py", "tests/*", "requirements.txt",
    )

    def set_version(self):
        self.version = load(self, os.path.join(self.recipe_folder, "VERSION")).strip()

    def requirements(self):
        self.requires("libsaturn/[>=0.1 <0.2]")

    def validate(self):
        if str(self.settings.os) != "baremetal" or str(self.settings.arch) != "sh2eb":
            raise ConanInvalidConfiguration(
                "ikemen-saturn builds for the Sega Saturn: use --profile:host=saturn-sh2eb "
                "(installed by `conan config install` from LibSaturn's packaging/conan/config)."
            )

    def layout(self):
        cmake_layout(self)

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_C_FLAGS_RELEASE"] = "-O2"
        tc.generate()

    def build(self):
        external = os.path.join(self.source_folder, ".external")
        if not os.path.isdir(os.path.join(external, "Ikemen-GO-Screenpack")):
            subprocess.run(
                [sys.executable, os.path.join(self.source_folder, "scripts", "fetch_external.py"),
                 "--dest", external],
                check=True)
        cmake = CMake(self)
        # Run the converters with the interpreter that runs Conan, so the
        # Pillow requirement above is the one that gets checked.
        cmake.configure(variables={"IKEMEN_EXTERNAL_DIR": external.replace("\\", "/"),
                                   "Python3_EXECUTABLE": sys.executable.replace("\\", "/")})
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.source_folder, os.path.join(self.package_folder, "licenses"))
        copy(self, "NOTICE.md", self.source_folder, os.path.join(self.package_folder, "licenses"))
        copy(self, "ikemen_saturn.app.bin", self.build_folder, os.path.join(self.package_folder, "bin"))
        copy(self, "ikemen_saturn.elf", self.build_folder, os.path.join(self.package_folder, "bin"))
        for pattern in ("ikemen_saturn.cue", "ikemen_saturn.bin", "ikemen_saturn.iso"):
            copy(self, pattern, os.path.join(self.build_folder, "disc"),
                 os.path.join(self.package_folder, "disc"))

    def package_info(self):
        self.cpp_info.bindirs = ["bin"]
        self.cpp_info.libdirs = []
        self.cpp_info.includedirs = []
