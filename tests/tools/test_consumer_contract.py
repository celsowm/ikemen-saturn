"""Guards the consumer boundary: LibSaturn is reached only as an installed package.

Static checks over this repository's own files (no LibSaturn needed):

* every #include is a system header, a `saturn/*` public header, or one of this
  project's own headers; nothing reaches into LibSaturn's `src/`, a private
  `.hpp`, or a parent directory;
* the build files never pull LibSaturn in by path: no add_subdirectory(),
  FetchContent/ExternalProject, sibling-checkout or `../` references.

When LIBSATURN_PREFIX is set, additionally checks that every `saturn/*` header
the sources include exists in the installed prefix.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INCLUDE = re.compile(r'^\s*#\s*include\s+([<"])([^>"]+)[>"]', re.M)
SOURCE_GLOBS = ("src/*.c", "src/*.h", "tests/host/*.cpp", "tools/ikemen_oracle/*.cpp")
CMAKE_FILES = [ROOT / "CMakeLists.txt", ROOT / "CMakePresets.json",
               *sorted((ROOT / "cmake").glob("*.cmake"))]


def own_headers() -> set:
    return {p.name for p in (ROOT / "src").glob("*.h")}


def check_includes() -> tuple:
    own = own_headers()
    problems = []
    seen = set()
    for pattern in SOURCE_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            for kind, name in INCLUDE.findall(text):
                where = f"{path.relative_to(ROOT)}: #include {name}"
                if kind == "<":
                    continue  # system / compiler header
                if name.startswith("saturn/") and name.endswith(".h"):
                    seen.add(name)
                elif name in own or name == "app_util.h":
                    pass
                elif name.startswith("ikemen_saturn/") and name.endswith(".h"):
                    pass  # generated into the build tree
                else:
                    problems.append(where)
    return problems, seen


def check_build_files() -> list:
    problems = []
    forbidden = [
        (re.compile(r"add_subdirectory\s*\(", re.I), "add_subdirectory"),
        (re.compile(r"FetchContent|ExternalProject", re.I), "FetchContent/ExternalProject"),
        (re.compile(r"\.\./|\.\.\\\\"), "parent-directory reference"),
        (re.compile(r"libsaturn[-_]?1|sibling", re.I), "sibling checkout"),
        (re.compile(r"/src/(core|graphics|hal|audio|input|physics|storage)\b"),
         "LibSaturn private source path"),
    ]
    for path in CMAKE_FILES:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".cmake" or path.name == "CMakeLists.txt":
            # Comments may name what is forbidden; only code counts.
            text = re.sub(r"(?m)#.*$", "", text)
        for pattern, label in forbidden:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert re.search(r"find_package\(\s*LibSaturn\b[^)]*CONFIG[^)]*REQUIRED", cmake), \
        "CMakeLists.txt must find LibSaturn with find_package(... CONFIG REQUIRED)"
    return problems


def main() -> int:
    problems, public_headers = check_includes()
    problems += check_build_files()
    assert not problems, "consumer boundary violated:\n  " + "\n  ".join(problems)
    assert public_headers, "expected the sources to include LibSaturn public headers"

    prefix = os.environ.get("LIBSATURN_PREFIX")
    if prefix:
        include_dir = Path(prefix) / "include"
        missing = [h for h in sorted(public_headers) if not (include_dir / h).is_file()]
        assert not missing, f"public headers not found in {include_dir}: {missing}"
    print("consumer contract: OK (%d public LibSaturn headers)" % len(public_headers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
