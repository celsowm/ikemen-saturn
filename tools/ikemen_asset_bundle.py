#!/usr/bin/env python3
"""Pack target-compiled, pointer-free asset tables into a Saturn bundle.

Table records are copied byte-for-byte from target object sections. The bundle
directory uses big-endian integers; table payloads retain the target ABI
representation and must be read on that target. Pointer-bearing root objects
must never be supplied as tables.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import tempfile
from pathlib import Path

MAGIC = b"IKBNDL\0\0"
VERSION = 1
HEADER = struct.Struct(">8sHHII")
ENTRY = struct.Struct(">HHIII")


def _ident(text: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in text)


def _macro_count(header: Path, name: str) -> int:
    text = header.read_text(encoding="utf-8")
    match = re.search(
        rf"(?m)^#define\s+{re.escape(name)}\s+(\d+)u?\s*$", text,
    )
    if not match:
        raise ValueError(f"missing {name} in {header}")
    return int(match.group(1))


def _compile_source(
    args: argparse.Namespace, source: Path, output: Path,
) -> None:
    includes = args.include_dir or []
    if args.generated_include_dir is not None:
        includes.append(args.generated_include_dir)
    command = [
        str(args.c_compiler), "-std=c11", "-m2", "-mb",
        "-ffreestanding", "-fdata-sections",
    ]
    command.extend(f"-I{include}" for include in includes)
    command.extend(["-c", str(source), "-o", str(output)])
    subprocess.run(command, check=True)


def _dump_section(objcopy: Path, obj: Path, section: str, output: Path) -> bytes:
    subprocess.run(
        [str(objcopy), f"--dump-section={section}={output}", str(obj)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return output.read_bytes()


def pack(args: argparse.Namespace) -> dict:
    sections = []
    seen: set[int] = set()
    with tempfile.TemporaryDirectory(prefix="ikemen-asset-bundle-") as temp:
        temp_path = Path(temp)
        section_specs = list(args.section or [])
        if args.cns_source is not None:
            object_path = temp_path / "character-cns.o"
            _compile_source(args, args.cns_source, object_path)
            section_specs.extend(cns_sections(
                object_path, args.cns_report, args.cns_header, args.symbol))

        if args.frames_source is not None:
            object_path = temp_path / "character-frames.o"
            _compile_source(args, args.frames_source, object_path)
            section_specs.extend(frame_sections(
                args.objcopy, object_path, args.frames_header,
                args.symbol, temp_path))

        if args.commands_source is not None:
            object_path = temp_path / "character-commands.o"
            _compile_source(args, args.commands_source, object_path)
            section_specs.extend(command_sections(
                object_path, args.commands_report, args.commands_header,
                args.symbol, temp_path))

        if args.state_rules_source is not None:
            object_path = temp_path / "character-state-rules.o"
            _compile_source(args, args.state_rules_source, object_path)
            section_specs.extend(state_rule_sections(
                object_path, args.state_rules_header, args.symbol))

        for section_id, object_name, section_name, count, alignment in section_specs:
            if section_id <= 0 or section_id > 0xFFFF:
                raise ValueError(f"invalid section id {section_id}")
            if section_id in seen:
                raise ValueError(f"duplicate section id {section_id}")
            if count < 0 or alignment not in (1, 2, 4, 8, 16, 32):
                raise ValueError("invalid section count or alignment")
            seen.add(section_id)
            payload = (
                object_name.read_bytes() if not section_name else
                _dump_section(
                    args.objcopy, object_name, section_name,
                    temp_path / f"section-{section_id}.bin",
                )
            )
            if not payload:
                raise ValueError(f"empty section {section_name}")
            sections.append({
                "id": section_id,
                "count": count,
                "alignment": alignment,
                "payload": payload,
                "source_object": str(object_name),
                "source_section": section_name,
            })

    sections.sort(key=lambda row: row["id"])
    directory_offset = HEADER.size
    payload_offset = directory_offset + ENTRY.size * len(sections)
    cursor = payload_offset
    for section in sections:
        cursor = (cursor + section["alignment"] - 1) & -section["alignment"]
        section["offset"] = cursor
        section["size"] = len(section["payload"])
        cursor += section["size"]
    if cursor > 0xFFFFFFFF:
        raise ValueError("bundle exceeds 4 GiB")

    output = bytearray(cursor)
    HEADER.pack_into(
        output, 0, MAGIC, VERSION, len(sections), directory_offset, cursor,
    )
    for index, section in enumerate(sections):
        ENTRY.pack_into(
            output,
            directory_offset + index * ENTRY.size,
            section["id"], section["alignment"], section["count"],
            section["offset"], section["size"],
        )
        start = section["offset"]
        output[start:start + section["size"]] = section["payload"]
        del section["payload"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    manifest = {
        "magic": MAGIC.rstrip(b"\0").decode("ascii"),
        "version": VERSION,
        "target_payload_endian": "big",
        "total_bytes": len(output),
        "sections": sections,
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    symbol = args.symbol or args.output.stem
    ident = "".join(char if char.isalnum() else "_" for char in symbol).upper()
    header_path = args.header_output or args.output.with_suffix(".h")
    header_path.parent.mkdir(parents=True, exist_ok=True)
    header_path.write_text(
        "/* Generated by tools/ikemen_asset_bundle.py. */\n"
        "#pragma once\n"
        f"#define {ident}_CHARACTER_BUNDLE_BYTES {len(output)}u\n"
        f"#define {ident}_CNS_BUNDLE_BYTES {len(output)}u\n"
        + (
            f"#define {ident}_FRAME_COUNT "
            f"{_macro_count(args.frames_header, ident + '_FRAME_COUNT')}u\n"
            f"#define {ident}_SPRITE_COUNT "
            f"{_macro_count(args.frames_header, ident + '_SPRITE_COUNT')}u\n"
            f"#define {ident}_PALETTE_COUNT "
            f"{_macro_count(args.frames_header, ident + '_PALETTE_COUNT')}u\n"
            f"#define {ident}_SPRITE_DATA_BYTES "
            f"{_macro_count(args.frames_header, ident + '_SPRITE_DATA_BYTES')}u\n"
            f"#define {ident}_MAX_SPRITE_BYTES "
            f"{_macro_count(args.frames_header, ident + '_MAX_SPRITE_BYTES')}u\n"
            f"#define {ident}_MAX_SPRITE_SOURCE_BYTES "
            f"{_macro_count(args.frames_header, ident + '_MAX_SPRITE_SOURCE_BYTES')}u\n"
            if args.frames_header is not None else ""
        ),
        encoding="utf-8",
    )
    return manifest


def cns_sections(
    obj: Path, report_path: Path, header_path: Path, symbol: str,
) -> list[tuple[int, Path, str, int, int]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    header = header_path.read_text(encoding="utf-8")
    ident = "".join(char if char.isalnum() else "_" for char in symbol)
    macro = ident.upper() + "_CNS_EXPRESSION_COUNT"
    match = re.search(
        rf"(?m)^#define\s+{re.escape(macro)}\s+(\d+)u?\s*$", header,
    )
    if not match:
        raise ValueError(f"missing {macro} in {header_path}")
    counts = (
        1, len(report["states"]), len(report["hitdefs"]),
        len(report["playsnds"]), len(report["controllers"]),
        len(report["helpers"]), len(report["reversals"]),
        len(report["hitoverrides"]), len(report["explods"]),
        len(report["projectiles"]), len(report["projectile_mods"]),
        int(match.group(1)),
    )
    names = (
        "cns_constants", "states", "hitdefs", "playsnds", "controllers",
        "helpers", "reversals", "hitoverrides", "explods", "projectiles",
        "projectile_mods", "expressions",
    )
    return [
        (section_id, obj, f".rodata.{ident}_{name}", count, 4)
        for section_id, (name, count) in enumerate(zip(names, counts), start=1)
    ]


def frame_sections(
    objcopy: Path, obj: Path, header_path: Path,
    symbol: str, temp_path: Path,
) -> list[tuple[int, Path, str, int, int]]:
    ident = _ident(symbol)
    upper = ident.upper()
    frames = _macro_count(header_path, upper + "_FRAME_COUNT")
    clsn = _macro_count(header_path, upper + "_CLSN_BOX_COUNT")
    sprites = _macro_count(header_path, upper + "_SPRITE_COUNT")
    palette_count = _macro_count(header_path, upper + "_PALETTE_COUNT")
    specs = [
        (20, obj, f".rodata.{ident}_frames", frames, 4),
        (21, obj, f".rodata.{ident}_clsn_boxes", clsn, 2),
        (22, obj, f".rodata.{ident}_sprites", sprites, 4),
    ]
    header = header_path.read_text(encoding="utf-8")
    names = re.findall(
        rf"(?m)^extern const uint16_t {re.escape(ident)}_palette_(\w+)\[256\];$",
        header,
    )
    if len(names) != palette_count or palette_count == 0:
        raise ValueError(f"palette declarations do not match count in {header_path}")
    palette_payload = bytearray()
    for index, name in enumerate(names):
        section = _dump_section(
            objcopy, obj, f".rodata.{ident}_palette_{name}",
            temp_path / f"palette-{index}.bin",
        )
        if len(section) != 512:
            raise ValueError(f"unexpected palette size for {name}: {len(section)}")
        palette_payload.extend(section)
    palette_path = temp_path / "character-palettes.bin"
    palette_path.write_bytes(palette_payload)
    specs.append((23, palette_path, "", palette_count * 256, 2))
    return specs


def command_sections(
    obj: Path, report_path: Path, header_path: Path,
    symbol: str, temp_path: Path,
) -> list[tuple[int, Path, str, int, int]]:
    ident = _ident(symbol)
    upper = ident.upper()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    specs = [
        (24, obj, f".rodata.{ident}_keys", report["key_count"], 4),
        (25, obj, f".rodata.{ident}_steps", report["step_count"], 4),
        (26, obj, f".rodata.{ident}_loop_order",
         sum(len(row["loop_order"]) for row in report["patterns"]), 1),
        (27, obj, f".rodata.{ident}_patterns", report["pattern_count"], 4),
    ]
    names = report["names"]
    grouped: dict[str, tuple[int, int]] = {}
    for index, pattern in enumerate(report["patterns"]):
        name = pattern["name"]
        if name not in grouped:
            grouped[name] = (index, 0)
        first, count = grouped[name]
        grouped[name] = (first, count + 1)
    strings = bytearray()
    refs = bytearray()
    for name in names:
        first, count = grouped[name]
        offset = len(strings)
        strings.extend(name.encode("utf-8"))
        strings.append(0)
        if first > 0xFFFF or count > 0xFF:
            raise ValueError(f"command name metadata overflows for {name!r}")
        refs.extend(struct.pack(">I H B B", offset, first, count, 0))
    refs_path = temp_path / "command-name-offsets.bin"
    strings_path = temp_path / "command-name-strings.bin"
    refs_path.write_bytes(refs)
    strings_path.write_bytes(strings)
    specs.extend([
        (28, refs_path, "", len(names), 4),
        (29, strings_path, "", len(strings), 1),
    ])
    return specs


def state_rule_sections(
    obj: Path, header_path: Path, symbol: str,
) -> list[tuple[int, Path, str, int, int]]:
    ident = _ident(symbol)
    upper = ident.upper()
    return [
        (30, obj, f".rodata.{ident}_state_rule_code",
         _macro_count(header_path, upper + "_STATE_RULE_INSTRUCTION_COUNT"), 4),
        (31, obj, f".rodata.{ident}_state_rule_rows",
         _macro_count(header_path, upper + "_STATE_RULE_COUNT"), 4),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objcopy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--header-output", type=Path)
    parser.add_argument(
        "--section", action="append", nargs=5,
        metavar=("ID", "OBJECT", "ELF_SECTION", "COUNT", "ALIGNMENT"),
        help="target object table to copy into the bundle; repeat per table",
    )
    parser.add_argument("--cns-object", type=Path)
    parser.add_argument("--cns-source", type=Path)
    parser.add_argument("--c-compiler", type=Path)
    parser.add_argument("--include-dir", action="append", type=Path, default=[])
    parser.add_argument("--generated-include-dir", type=Path)
    parser.add_argument("--cns-report", type=Path)
    parser.add_argument("--cns-header", type=Path)
    parser.add_argument("--frames-source", type=Path)
    parser.add_argument("--frames-header", type=Path)
    parser.add_argument("--commands-source", type=Path)
    parser.add_argument("--commands-header", type=Path)
    parser.add_argument("--commands-report", type=Path)
    parser.add_argument("--state-rules-source", type=Path)
    parser.add_argument("--state-rules-header", type=Path)
    parser.add_argument("--symbol")
    args = parser.parse_args()
    explicit = [
        (int(section_id, 0), Path(object_name), section_name,
         int(count, 0), int(alignment, 0))
        for section_id, object_name, section_name, count, alignment
        in (args.section or [])
    ]
    groups = (
        ((args.cns_source, args.cns_report, args.cns_header), "CNS"),
        ((args.frames_source, args.frames_header), "frame"),
        ((args.commands_source, args.commands_report,
          args.commands_header), "command"),
        ((args.state_rules_source, args.state_rules_header), "state-rule"),
    )
    for values, label in groups:
        if any(value is not None for value in values) and any(
                value is None for value in values):
            parser.error(f"all {label} bundle inputs are required")
    if args.cns_object is not None:
        if any(value is not None for value in (
                args.cns_source, args.frames_source, args.commands_source,
                args.state_rules_source)):
            parser.error("--cns-object cannot be combined with source inputs")
        if any(value is None for value in (
                args.cns_report, args.cns_header, args.symbol)):
            parser.error("--cns-object requires CNS report, header, and symbol")
        explicit.extend(cns_sections(
            args.cns_object, args.cns_report, args.cns_header, args.symbol))
    generated = any(value is not None for value in (
        args.cns_source, args.frames_source, args.commands_source,
        args.state_rules_source))
    if generated and any(value is None for value in (
            args.c_compiler, args.symbol)):
        parser.error("generated tables require compiler, include dir, and symbol")
    if generated and not args.include_dir:
        parser.error("generated tables require at least one include dir")
    if not explicit and not generated:
        parser.error("provide --section or generated asset inputs")
    args.section = explicit
    manifest = pack(args)
    print(
        f"[ikemen_asset_bundle] sections={len(manifest['sections'])} "
        f"bytes={manifest['total_bytes']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
