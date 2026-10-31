# Ikemen Saturn

Kung Fu Man vs ZSS Kung Fu Man on a Sega Saturn, running the original
Ikemen GO / MUGEN character data and measured against upstream Ikemen GO
**frame by frame**: 66 KFM gameplay oracle scenarios compare positions,
velocities, states, animations, contacts and RNG against an instrumented build
of the real engine. The gameplay matrix is 1:1 for the covered KFM scope:
movement, normals, specials, supers, combos, throws, guard/reversal, recovery,
get-up, KO, timeout/draw/win flow and taunt. HUD/motif presentation and broader
generic Ikemen compatibility remain separate work.

It is an independent consumer of [LibSaturn](https://github.com/celsowm/libsaturn):
it reaches the library only through the installed CMake/Conan package contract
(`find_package(LibSaturn CONFIG)`, `LibSaturn::Saturn`, `libsaturn_add_disc`).
There is no sibling checkout, no `add_subdirectory`, and no LibSaturn private
header or build-tree path anywhere in this repository.

The shared frame driver accepts independent CNS, AIR, CMD and State -1
tables for each fighter, configuring the match from one consistent bundle per
player. The playable demo now gives P2 the original ZSS CMD, .const and AIR/SFF
while retaining classic KFM CNS state bodies and State -1 rules as a
temporary compatibility bridge. ZSS's actual script-based gameplay/AI is
not yet implemented or covered by the 66 classic-KFM oracle scenarios.
The build compiles all 36 directly guarded `command.zss` State -1
ChangeState branches (including AnimElemTime cancel tests) and activates them
for human-controlled P2. The importer rejects incomplete coverage.
Forty-three ZSS state bodies now have source-checked native lowering:
170, 180, 195, 200, 210, 230, 240, 400, 410, 430, 440, 600, 610, 630, 640, 1000, 1010, 1020, 1050, 1051, 1052, 1055, 1056, 1060, 1061, 1070, 1071, 1075, 1100, 1110, 1120, 1200, 1210, 1220, 1400, 1410 and 1420 (from kfm.zss), and 820, 821, 1025, 1026, 1027,
1028 (from hits.zss). State 1061 preserves Strong Knee's prior HitDef,
accepts human A/B air-kick cancels into 1055 and lands through 1052.
The 821 human recovery path is ported; AI random recovery remains deferred.
1027 and 1028 now have source-checked native wall-impact, F72 FightFX,
common SysSnd(7,0), wall-bounce and descending animation logic.
All 59 kfm.zss/hits.zss StateDefs are now source-checked native lowerings
(the former 191, 800, 810, 1300-1351 and 3000/3050/3051 included); none keeps
the classic-CNS fallback. The human-input KFM-vs-ZSS oracle matrix (49
scenarios plus the intro, throw, blocking and hyper probes) matches upstream
frame for frame. The shipped CPU opponent is the bounded native CPU
(neutral movement, parry/guard, anti-air and hit-confirm cancels); exact
AI.zss parity (global RNG order, AI_JI, opponent memory, 821 random recovery)
is an explicit non-goal of this port, not a pending item. See
`docs/IKEMEN_COMPAT.md`.

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

Controls: D-pad move/crouch/jump, X/Y punches, A/B kicks, START taunt.
Without a second pad, P2 runs the native ZSS CPU neutral subset (walk,
run, stop and standing/crouching light attacks). Connecting the second pad
restores human P2 input. This is **not full AI or upstream RNG parity**.
Oracle/host runners keep P2 idle by default unless CPU is opted into.

For a reproducible headless injection smoke test on any platform with the
LibSaturn Ymir probe, run:

```sh
python3 scripts/saturn_smoke.py --probe /path/to/probe --bios /path/to/bios.bin \
    --nm /path/to/sh2eb-elf-nm --out build/saturn/smoke
```

The output directory must not already exist. It contains the probe log and
report, a screenshot, a panic dump and a summary with build and input hashes.
This checks injected execution, not disc boot or gameplay parity.

To record a real CD boot in Mednafen with an isolated profile and a 4 MiB
cartridge, use a fresh output directory:

```sh
python3 scripts/record_mednafen.py --bios /path/to/bios.bin \
    --out build/saturn/mednafen-run --seconds 30 --screenshots 10 22
```

The recording and extracted frames must be inspected to establish what the
game reached; a successful process exit alone does not prove gameplay.

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

### Bounded ZSS CPU defense and cancels

The unplugged P2 CPU now also tries close parries, guarded back input,
anti-air Kung Fu Upper and hit-confirmed normal/special/super cancels.
These decisions reuse authored attack states and are not a claim of
frame-by-frame Ikemen GO autonomous AI equivalence. See
`docs/IKEMEN_COMPAT.md` for the still-missing AI predicates and RNG.
