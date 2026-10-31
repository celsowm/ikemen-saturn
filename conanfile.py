"""Conan 2 recipe for Ikemen Saturn.

IkemenSaturn C library: `requires("ikemen-saturn")` + `requires("libsaturn")`.
The recipe builds and packages the static library and CMake config.

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

    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"

    exports_sources = (
        "CMakeLists.txt", "VERSION", "LICENSE", "NOTICE.md",
        "cmake/*", "src/*", "tools/*", "scripts/external-pins.env",
        "scripts/fetch_external.py", "tests/*", "requirements.txt",
        "include/*",
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
        # Library and headers are installed by CMake install() rules
        # Just ensure the CMake config is copied
        for pattern in ("*.cmake",):
            copy(self, pattern,
                 os.path.join(self.build_folder, "lib", "cmake", "IkemenSaturn"),
                 os.path.join(self.package_folder, "lib", "cmake", "IkemenSaturn"))

    def package_info(self):
        self.cpp_info.libs = ["ikemen_saturn"]
        self.cpp_info.includedirs = ["include"]
        self.cpp_info.libdirs = ["lib"]
        # The CMake config is in lib/cmake/IkemenSaturn
        self.cpp_info.set_property("cmake_target_name", "IkemenSaturn::IkemenSaturn")
        # Requires LibSaturn::Core transitively (handled by CMake config)
        self.cpp_info.requires = ["libsaturn::libsaturn"]