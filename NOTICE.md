# Notices

## This repository's code

The Saturn runtime (`src/`), the converters (`tools/`), the build files and the
tests are MIT licensed; see `LICENSE`.

## Game data is not part of this repository

No upstream asset is committed here. The build fetches two checkouts at the
commits pinned in `scripts/external-pins.env` and converts them offline into C
tables and disc blobs under the build tree:

| Checkout | Used for | Licence |
|---|---|---|
| [Ikemen-GO-Screenpack](https://github.com/ikemen-engine/Ikemen-GO-Screenpack) | Kung Fu Man and ZSS Kung Fu Man sprites, animations, commands, constants and sounds; fight effects; stage 0 | See `LICENCE.txt` in that repository: contributed art is CC BY 3.0, the Mugen font files are CC BY-NC 3.0. Kung Fu Man originates from Elecbyte. |
| [Ikemen-GO](https://github.com/ikemen-engine/Ikemen-GO) | `data/common1.cns.zss` (common states); the oracle runs the engine itself | MIT, see `LICENCE.txt` in that repository |

Disc images built from this repository contain converted Screenpack data, so
redistributing a built disc carries the upstream attribution and licence terms
above (including the non-commercial restriction on any CC BY-NC content you
enable). The converters and the oracle do not change those terms.

## Libraries

- [LibSaturn](https://github.com/celsowm/libsaturn) (MIT): the Saturn runtime
  library, consumed only as an installed CMake/Conan package.

## Tools used for validation, not redistributed

The Ymir emulator probe from LibSaturn's `harness/` (GPL-3.0) is used by
`scripts/run-emulator.ps1` when you point it at a built probe; it is neither
built nor shipped here. A Saturn BIOS dump is required to run it and is not
provided.
