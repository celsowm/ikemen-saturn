# Changelog

## 0.1.0 (unreleased)

Initial extraction from LibSaturn's `examples/ikemen_saturn`.

- Standalone CMake project that consumes LibSaturn only through its installed
  package (`find_package(LibSaturn CONFIG)`, `libsaturn_add_disc`), with
  `saturn` (firmware + bootable disc) and `host` (tests + oracle trace)
  presets and a Conan 2 recipe.
- Generated assets are build outputs of the converters in `tools/`, produced
  from upstream data pinned in `scripts/external-pins.env`.
- The upstream Ikemen GO oracle (`tools/ikemen_oracle`) and its 63 scenarios
  moved with the runtime; the Saturn side is built by the `host` preset.
- Behavior is unchanged from the in-tree example: scripted emulator runs of the
  old and new builds produce byte-identical screenshots.
