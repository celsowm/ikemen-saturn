# Ikemen Saturn

Kung Fu Man vs ZSS Kung Fu Man on a Sega Saturn, running the original
Ikemen GO / MUGEN character data and measured against upstream Ikemen GO
**frame by frame**: 63 oracle scenarios (61 passing, 2 marked `pending` for
the unfinished KO flow) compare positions, velocities, states, animations,
contacts and RNG against an instrumented build of the real engine.

It is an independent consumer of [LibSaturn](https://github.com/celsowm/libsaturn):
it reaches the library only through the installed CMake/Conan package contract
(`find_package(LibSaturn CONFIG)`, `LibSaturn::Saturn`, `libsaturn_add_disc`).
There is no sibling checkout, no `add_subdirectory`, and no LibSaturn private
header or build-tree path anywhere in this repository.

## Requirements

- An installed LibSaturn package (a `cmake --install` prefix, or the Conan
  package). Set `LIBSATURN_PREFIX` to it.
- The `sh2eb-elf` GCC toolchain on `PATH`, CMake 3.24+, Ninja, Python 3.10+,
  and `mkisofs`/`genisoimage`/`xorrisofs` for the disc image.
- `pip install -r requirements.txt` (Pillow, used by the sprite converters).
- Network access once, to fetch the pinned upstream data (below).
- Optional, for the oracle: Go, SDL2, libxmp and ffmpeg dev packages
  (MSYS2 ucrt64 or Linux). See `docs/IKEMEN_COMPAT.md`.

## Build the disc

```sh
python scripts/fetch_external.py            # pinned Ikemen-GO + Screenpack -> .external/
export LIBSATURN_PREFIX=/path/to/libsaturn  # the installed package
cmake --preset saturn
cmake --build --preset saturn
```

Outputs under `build/saturn/`: `ikemen_saturn.elf`, `ikemen_saturn.app.bin`
(must stay under 983040 bytes) and `disc/ikemen_saturn.{iso,bin,cue}`.

The game needs a **4 MiB RAM expansion cartridge**.

With Conan instead of a CMake prefix:

```sh
conan config install <libsaturn>/packaging/conan/config
conan create <libsaturn> --profile:host=saturn-sh2eb --profile:build=default
conan create .           --profile:host=saturn-sh2eb --profile:build=default
```

## Run it

`scripts/run-emulator.ps1` boots the disc in LibSaturn's Ymir probe (a separate
tool, not vendored here) with the 4 MiB cart and optional scripted input and
screenshots:

```powershell
$env:IKEMEN_PROBE   = 'path\to\probe.exe'
$env:LIBSATURN_BIOS = 'path\to\saturn_bios_us.bin'   # your own dump
scripts\run-emulator.ps1 -Frames 700 -PadScript scripts\pads\ikemen_kick.pad `
    -Screenshot 380:build\shots\idle.png
```

Controls: D-pad move/crouch/jump, X/Y punches, A/B kicks, START taunt; plug in a
second pad to control P2.

## Test

```sh
cmake --preset host
cmake --build --preset host
ctest --preset host                         # 10 C++ unit tests + 8 Python tool tests
cmake --build build/host --target ikemen_oracle_suite   # full upstream oracle (long)
```

The `host` preset uses the native compiler and only the installed LibSaturn
*headers*. The oracle's Saturn side (`ikemen_oracle_trace`) is the same
`src/ikemen_*.c` logic the console runs, driven by the same `ik_frame_step()`.

## Layout

| Path | What |
|---|---|
| `src/` | Saturn runtime: fight logic (`ikemen_fight*.c`), CNS/CMD/expression VMs, entity pool, firmware entry (`main.c`) |
| `tools/ikemen_*` | Offline converters (SFF/AIR/SND/CMD/CNS to C tables and disc blobs) |
| `tools/ikemen_oracle/` | Upstream Ikemen GO oracle: instrumentation, scenarios, trace diff |
| `cmake/` | Source lists and generated-asset rules |
| `tests/` | Host unit tests (`host/`) and converter/oracle tool tests (`tools/`) |
| `docs/` | Architecture and fidelity notes, compatibility status |

## Licences

Code: MIT (`LICENSE`). No upstream asset is committed; see `NOTICE.md` for the
data this build fetches and the terms that apply to discs built from it.
