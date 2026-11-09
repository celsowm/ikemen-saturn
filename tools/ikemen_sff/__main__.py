"""CLI wiring for the Ikemen -> Saturn asset pipeline.

Modes:
  char   --sff K.sff --air K.air --actions 0,20,40 --palettes 1,4
           Emits <prefix>_frames.c/.h (metadata + palettes) and a packed
           sprite payload binary selected by --sprite-bin.
  fx     --sff fightfx.sff --air fightfx.air --actions 0,1,2,3,40
           Preserves each referenced sprite's SFF palette and AIR drawtype.
  stage  --sff S.sff --layers "0,0:start0,0:tile;0,1:start0,185:tile"
           Emits <prefix>_plane.c/.h (320x224 indexed canvas + palette).

Both modes also write <prefix>.json (manifest: stats, warnings) and,
with --png-dir, debug PNG renders for visual inspection.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import air as air_mod
from . import emit as emit_mod
from . import palettes as pal_mod
from . import sff as sff_mod
from . import stage as stage_mod
from .codecs import decode, UnsupportedCodec

PALETTE_NODE_MAIN = 0  # sprite palidx 0 -> palette node 0
AIR_BLANK_SPRITE = (-1, -1)


def _blank_sprite_asset() -> emit_mod.SpriteAsset:
    """Return a transparent texel for AIR elements that request no sprite."""
    return emit_mod.SpriteAsset(
        width=1, height=1, padded_width=8, left_pad=3,
        format=sff_mod.FORMAT_RAW, data=b"\x00")


def _load_palette(container: sff_mod.SffContainer, group: int, number: int):
    for i, node in enumerate(container.palette_nodes()):
        if node.group == group and node.number == number:
            return i, pal_mod.materialize(container, node)
    raise SystemExit(f"[ikemen_sff] palette ({group},{number}) not found", 2)


def _png_dump_indexed(path: Path, pixels, width: int, height: int,
                      palette: list[int]) -> None:
    from PIL import Image
    img = Image.frombytes("P", (width, height), bytes(pixels))
    rgb = bytearray()
    for w in palette:
        b = (w >> 10) & 0x1F
        g = (w >> 5) & 0x1F
        r = w & 0x1F
        rgb += bytes((r << 3, g << 3, b << 3))
    img.putpalette(bytes(rgb[:768]))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _pad_sprite(pixels: bytes, width: int, height: int):
    """VDP1 textures need a width that is a multiple of 8: the sprite is
    centered inside the padded box and the transparent pads are index 0.
    Returns (pixels, padded_width, left_pad); adding left_pad to the
    sprite axis keeps horizontal flip math exact (symmetric box)."""
    padded = (width + 7) & ~7
    if padded == width:
        return bytes(pixels), width, 0
    left = (padded - width) // 2
    out = bytearray(padded * height)
    for row in range(height):
        out[row * padded + left:row * padded + left + width] = \
            pixels[row * width:row * width + width]
    return bytes(out), padded, left


def _assign_v1_palettes(container, sprite_assets: dict) -> None:
    """Resolve each sprite's palette words in file order.

    SFF v1 stores the character's palette once per sprite block, but most
    body sprites merely point at the previous sprite's palette (ps byte at
    node+18, see Ikemen-GO read(): paletteSame). Walk the file list and
    hand out resolved palettes, falling back to the previous palette for
    ps != 0 sprites and to the alias target's palette for size == 0
    placeholders (link = list index).
    """
    nodes = list(container.sprite_nodes())
    palettes: list[list[int] | None] = [None] * len(nodes)
    last_palette: list[int] | None = None
    for index, node in enumerate(nodes):
        if node.data_length == 0:
            link = node.palette_link
            palettes[index] = palettes[link] if 0 <= link < index else None
            continue
        if node.fmt != sff_mod.FORMAT_PCX:
            continue
        if node.ps != 0 and last_palette is not None:
            palettes[index] = last_palette
            continue
        own = _pcx_palette(container.sprite_data(node))
        if own is not None:
            palettes[index] = own
            last_palette = own
        # else: no palette found, leave None and keep last_palette
    by_key: dict[tuple[int, int], int] = {}
    for index, node in enumerate(nodes):
        by_key.setdefault((node.group, node.number), index)
    for key, sprite in sprite_assets.items():
        index = by_key.get(key)
        if index is None:
            continue
        node = nodes[index]
        # Aliases (size == 0) resolved to their target during decode; take
        # the alias target's palette, matching the pixel payload.
        if node.data_length == 0:
            link = node.palette_link
            if 0 <= link < len(palettes):
                sprite.palette_words = palettes[link]
            continue
        sprite.palette_words = palettes[index]


def _load_act_palettes(spec: str) -> list[list[int]]:
    """Loads 768-byte .act palette files (raw RGB triples, forward order,
    palette index 0 treated as transparent) and returns BGR555 words."""
    palettes: list[list[int]] = []
    for entry in spec.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        raw = Path(entry).read_bytes()
        if len(raw) != 768:
            raise SystemExit(f"[ikemen_sff] .act palette must be 768 bytes: {entry} ({len(raw)})", 2)
        words = [pal_mod.BLACK] * 256
        for i in range(256):
            r, g, b = raw[i * 3:(i + 1) * 3]
            words[i] = ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
        words[0] = pal_mod.BLACK
        palettes.append(words)
    return palettes


def _pcx_palette(data: bytes) -> list[int] | None:
    """Extracts a 256-entry BGR555 palette from 8-bit PCX sprite data.

    The palette is the last 768 bytes of the payload, behind a 0x0C marker
    on regular sprites (see codecs.pcx_palette_offset). Embedded palettes
    are read forward; the reverse-order rule only applies to external .act
    files, which this pipeline does not read. Index 0 stays transparent.
    """
    from .codecs import pcx_palette_offset

    if len(data) < 768:
        return None
    offset = pcx_palette_offset(data)
    if offset is None:
        return None
    raw = data[offset:offset + 768]
    if len(raw) < 768:
        return None
    words = [pal_mod.BLACK] * pal_mod.ENTRY_COUNT
    for i in range(pal_mod.ENTRY_COUNT):
        r, g, b = raw[i * 3:(i + 1) * 3]
        words[i] = ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
    words[0] = pal_mod.BLACK
    return words


def _runtime_sprite_asset(container: sff_mod.SffContainer,
                          node: sff_mod.SpriteNode,
                          all_nodes: list[sff_mod.SpriteNode] | None = None,
                          node_index: int | None = None) -> emit_mod.SpriteAsset:
    # SFF v2's link field refers to an earlier sprite when data_length == 0.
    # Ikemen shares that source texture/size while retaining the destination
    # sprite's own axis and palette selection.
    source_node = node
    source_index = node_index
    seen: set[int] = set()
    while (all_nodes is not None and source_index is not None and
           source_node.data_length == 0):
        link = source_node.palette_link
        if link >= source_index or link >= len(all_nodes) or link in seen:
            break
        seen.add(link)
        source_node = all_nodes[link]
        source_index = link

    source = container.sprite_data(source_node)
    raw = decode(source_node, source)
    if len(raw) != source_node.width * source_node.height:
        raise ValueError(
            f"sprite {(node.group, node.number)} decoded size mismatch")

    if source_node.fmt == sff_mod.FORMAT_RAW or (
            source_node.fmt == sff_mod.FORMAT_LZ5 and source):
        payload = source
        runtime_format = source_node.fmt
    else:
        # Formats unsupported by the tiny Saturn decoder are lowered offline.
        # Invalid empty links keep the legacy deterministic zero-sprite path.
        payload = raw
        runtime_format = sff_mod.FORMAT_RAW

    padded_w = (source_node.width + 7) & ~7
    left = (padded_w - source_node.width) // 2
    # (SFF v1 palettes are assigned in a file-order pass afterwards; see
    # _assign_v1_palettes.)
    return emit_mod.SpriteAsset(
        width=source_node.width,
        height=source_node.height,
        padded_width=padded_w,
        left_pad=left,
        format=runtime_format,
        data=bytes(payload),
        xoff=node.xoff,
        yoff=node.yoff,
    )


def _indexed_nodes(container: sff_mod.SffContainer):
    all_nodes = list(container.sprite_nodes())
    by_key: dict[tuple[int, int], tuple[int, sff_mod.SpriteNode]] = {}
    for index, node in enumerate(all_nodes):
        # Match Ikemen: the first duplicate group/number wins.
        by_key.setdefault((node.group, node.number), (index, node))
    return all_nodes, by_key


def cmd_char(args) -> int:
    container = sff_mod.load(Path(args.sff))
    actions = air_mod.parse(Path(args.air))
    all_nodes, nodes = _indexed_nodes(container)

    frames: list[emit_mod.FrameAsset] = []
    sprite_assets: dict[tuple[int, int], emit_mod.SpriteAsset] = {}
    missing: list[str] = []
    for action in args.actions:
        act = actions.get(action)
        if act is None or not act.frames:
            missing.append(str(action))
            continue
        for idx, fr in enumerate(act.frames):
            no_sprite = fr.group < 0 or fr.number < 0
            source_key = (fr.group, fr.number)
            entry = None if no_sprite else nodes.get(source_key)
            if not no_sprite and entry is None:
                missing.append(f"{action}:{fr.group},{fr.number}")
                no_sprite = True
            key = AIR_BLANK_SPRITE if no_sprite else source_key
            if no_sprite:
                node_index, node = None, None
            else:
                node_index, node = entry
            if key not in sprite_assets:
                if no_sprite:
                    sprite_assets[key] = _blank_sprite_asset()
                else:
                    try:
                        sprite_assets[key] = _runtime_sprite_asset(
                            container, node, all_nodes, node_index)
                    except UnsupportedCodec as exc:
                        raise SystemExit(f"[ikemen_sff] {key}: {exc}", 2)
            sprite = sprite_assets[key]
            frames.append(emit_mod.FrameAsset(
                action=action, index=idx,
                width=sprite.padded_width, height=sprite.height,
                ax=(node.xoff if node else 0) + sprite.left_pad - fr.x,
                ay=(node.yoff if node else 0) - fr.y, ticks=fr.time,
                flip_h=fr.flip_h, flip_v=fr.flip_v,
                sprite_key=key, air_x=fr.x, air_y=fr.y,
                blend_mode=fr.blend_mode,
                loop_start=(act.loop_start == idx),
                clsn1=list(fr.clsn1), clsn2=list(fr.clsn2)))
    if not frames:
        raise SystemExit("[ikemen_sff] no frames resolved", 2)

    if container.version == 1:
        if args.act_palettes:
            # .def-defined palettes (e.g. chars/KULA/act/kula-A.act) replace
            # the embedded ones; every sprite indexes the first palette.
            act_palettes = _load_act_palettes(args.act_palettes)
            if not act_palettes:
                raise SystemExit("[ikemen_sff] --act-palettes produced no palettes", 2)
            for sprite in sprite_assets.values():
                sprite.palette_index = 0
            names = {f"p{i}": words for i, words in enumerate(act_palettes)}
        else:
            _assign_v1_palettes(container, sprite_assets)
            palette_map: dict[tuple[int, ...], int] = {}
            palettes: list[list[int]] = []
            for sprite in sprite_assets.values():
                if sprite.palette_words is None:
                    continue
                key = tuple(sprite.palette_words)
                if key not in palette_map:
                    palette_map[key] = len(palettes)
                    palettes.append(sprite.palette_words)
                sprite.palette_index = palette_map[key]
            names = {f"p{i}": words for i, words in enumerate(palettes)}
            if not names:
                raise SystemExit("[ikemen_sff] no v1 palettes extracted", 2)
    else:
        main_pal_idx, main_palette = _load_palette(
            container, args.palettes[0][0], args.palettes[0][1])
        alt_palettes = {}
        for i, key in enumerate(args.palettes[1:], start=1):
            _, words = _load_palette(container, key[0], key[1])
            alt_palettes[f"alt{i}"] = words
        names = {"main": main_palette, **alt_palettes}
    c_text, h_text, sprite_blob = emit_mod.emit_frames(
        args.out_prefix, args.symbol, frames, sprite_assets, names,
        Path(args.sff).name)
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    (out_prefix.parent / f"{out_prefix.name}_frames.c").write_text(c_text, encoding="utf-8")
    (out_prefix.parent / f"{out_prefix.name}_frames.h").write_text(h_text, encoding="utf-8")
    sprite_bin = Path(args.sprite_bin) if args.sprite_bin else (
        out_prefix.parent / f"{out_prefix.name}_sprites.bin")
    sprite_bin.parent.mkdir(parents=True, exist_ok=True)
    sprite_bin.write_bytes(sprite_blob)

    raw_blob = sum(s.padded_width * s.height for s in sprite_assets.values())
    packed_blob = sum(len(s.data) for s in sprite_assets.values())
    max_sprite = max(s.padded_width * s.height for s in sprite_assets.values())
    manifest = {
        "symbol": args.symbol,
        "sff": args.sff,
        "air": args.air,
        "actions": {str(a): len(actions[a].frames)
                    for a in args.actions if a in actions},
        "frames": len(frames),
        "unique_sprites": len(sprite_assets),
        "pixel_bytes": raw_blob,
        "packed_pixel_bytes": packed_blob,
        "stored_pixel_bytes": len(sprite_blob),
        "sprite_blob": str(sprite_bin),
        "max_sprite_bytes": max_sprite,
        "max_sprite_source_bytes": max(len(s.data) for s in sprite_assets.values()),
        "clsn1_default": {str(a): actions[a].clsn1_default
                           for a in args.actions if a in actions},
        "clsn2_default": {str(a): actions[a].clsn2_default
                           for a in args.actions if a in actions},
        "missing": missing,
    }
    (out_prefix.parent / f"{out_prefix.name}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    if args.png_dir:
        for key in list(sprite_assets)[:args.png_limit]:
            if key == AIR_BLANK_SPRITE or key not in nodes:
                raw, width, height = b"\x00", 1, 1
            else:
                _, node = nodes[key]
                raw = decode(node, container.sprite_data(node))
                width, height = node.width, node.height
            pixels, padded_w, _ = _pad_sprite(raw, width, height)
            _png_dump_indexed(Path(args.png_dir) / f"{key[0]}_{key[1]}.png",
                              pixels, padded_w, height, main_palette)
    print(f"[ikemen_sff] char {args.symbol}: frames={len(frames)} "
          f"unique={len(sprite_assets)} raw={raw_blob}B packed={packed_blob}B "
          f"missing={missing or 'none'}")
    return 0


def cmd_fx(args) -> int:
    container = sff_mod.load(Path(args.sff))
    actions = air_mod.parse(Path(args.air))
    all_nodes, nodes = _indexed_nodes(container)

    frames: list[emit_mod.FrameAsset] = []
    sprite_assets: dict[tuple[int, int], emit_mod.SpriteAsset] = {}
    palette_slots: dict[tuple[int, ...], int] = {}
    palette_words: list[list[int]] = []
    missing: list[str] = []

    for action in args.actions:
        act = actions.get(action)
        if act is None or not act.frames:
            missing.append(str(action))
            continue
        for idx, fr in enumerate(act.frames):
            no_sprite = fr.group < 0 or fr.number < 0
            source_key = (fr.group, fr.number)
            entry = None if no_sprite else nodes.get(source_key)
            if not no_sprite and entry is None:
                missing.append(f"{action}:{fr.group},{fr.number}")
                no_sprite = True
            key = AIR_BLANK_SPRITE if no_sprite else source_key
            if no_sprite:
                node_index, node = None, None
            else:
                node_index, node = entry
            if key not in sprite_assets:
                if no_sprite:
                    sprite = _blank_sprite_asset()
                    if not palette_words:
                        words = pal_mod.materialize_index(container, 0)
                        palette_words.append(words)
                        palette_slots[tuple(words)] = 0
                    sprite.palette_index = 0
                else:
                    try:
                        sprite = _runtime_sprite_asset(
                            container, node, all_nodes, node_index)
                    except UnsupportedCodec as exc:
                        raise SystemExit(f"[ikemen_sff] {key}: {exc}", 2)
                    palette_index = (
                        node.palette_index
                        if node.palette_index < container.palette_count
                        else 0
                    )
                    words = pal_mod.materialize_index(container, palette_index)
                    pal_key = tuple(words)
                    palette_index = palette_slots.get(pal_key)
                    if palette_index is None:
                        palette_index = len(palette_words)
                        palette_slots[pal_key] = palette_index
                        palette_words.append(words)
                    sprite.palette_index = palette_index
                sprite_assets[key] = sprite

            sprite = sprite_assets[key]
            frames.append(emit_mod.FrameAsset(
                action=action, index=idx,
                width=sprite.padded_width, height=sprite.height,
                ax=(node.xoff if node else 0) + sprite.left_pad - fr.x,
                ay=(node.yoff if node else 0) - fr.y, ticks=fr.time,
                flip_h=fr.flip_h, flip_v=fr.flip_v,
                sprite_key=key, air_x=fr.x, air_y=fr.y,
                blend_mode=fr.blend_mode,
                loop_start=(act.loop_start == idx),
                clsn1=list(fr.clsn1), clsn2=list(fr.clsn2)))

    if not frames:
        raise SystemExit("[ikemen_sff] no effect frames resolved", 2)
    if len(palette_words) > 0xFFFF:
        raise SystemExit("[ikemen_sff] too many effect palettes", 2)

    names = {f"p{i}": words for i, words in enumerate(palette_words)}
    c_text, h_text, sprite_blob = emit_mod.emit_frames(
        args.out_prefix, args.symbol, frames, sprite_assets, names,
        Path(args.sff).name)

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    (out_prefix.parent / f"{out_prefix.name}_frames.c").write_text(
        c_text, encoding="utf-8")
    (out_prefix.parent / f"{out_prefix.name}_frames.h").write_text(
        h_text, encoding="utf-8")
    sprite_bin = Path(args.sprite_bin) if args.sprite_bin else (
        out_prefix.parent / f"{out_prefix.name}_sprites.bin")
    sprite_bin.parent.mkdir(parents=True, exist_ok=True)
    sprite_bin.write_bytes(sprite_blob)

    manifest = {
        "symbol": args.symbol,
        "sff": args.sff,
        "air": args.air,
        "actions": {str(a): len(actions[a].frames)
                    for a in args.actions if a in actions},
        "frames": len(frames),
        "unique_sprites": len(sprite_assets),
        "palettes": len(palette_words),
        "sprite_blob": str(sprite_bin),
        "stored_pixel_bytes": len(sprite_blob),
        "max_sprite_bytes": max(
            s.padded_width * s.height for s in sprite_assets.values()),
        "max_sprite_source_bytes": max(
            len(s.data) for s in sprite_assets.values()),
        "missing": missing,
    }
    (out_prefix.parent / f"{out_prefix.name}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[ikemen_sff] fx {args.symbol}: frames={len(frames)} "
          f"unique={len(sprite_assets)} palettes={len(palette_words)} "
          f"stored={len(sprite_blob)}B missing={missing or 'none'}")
    return 0



def cmd_stage(args) -> int:
    container = sff_mod.load(Path(args.sff))
    layers = []
    for spec in args.layers.split(";"):
        spec = spec.strip()
        if not spec:
            continue
        parts = spec.split(":")
        group, number = (int(v) for v in parts[0].split(","))
        layer = stage_mod.StageLayer(sprite=(group, number))
        for opt in parts[1:]:
            if opt.startswith("start"):
                sx, sy = (int(v) for v in opt.split("=")[1].split(","))
                layer.start = (sx, sy)
            elif opt == "tile":
                layer.tile_x = True
        layers.append(layer)
    stage = stage_mod.compose(container, layers)

    c_text, h_text = emit_mod.emit_stage(
        args.out_prefix, args.symbol, stage, Path(args.sff).name)
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    (out_prefix.parent / f"{out_prefix.name}_plane.c").write_text(c_text, encoding="utf-8")
    (out_prefix.parent / f"{out_prefix.name}_plane.h").write_text(h_text, encoding="utf-8")

    (out_prefix.parent / f"{out_prefix.name}.json").write_text(json.dumps({
        "symbol": args.symbol,
        "sff": args.sff,
        "layers": [str(l.sprite) for l in layers],
        "width": stage.width,
        "height": stage.height,
        "warnings": stage.warnings,
    }, indent=2), encoding="utf-8")

    if args.png_dir:
        _png_dump_indexed(Path(args.png_dir) / f"{args.symbol}.png",
                          stage.pixels, stage.width, stage.height, stage.palette)
    print(f"[ikemen_sff] stage {args.symbol}: {stage.width}x{stage.height} "
          f"pixels={len(stage.pixels)}B warnings={stage.warnings or 'none'}")
    return 0


def _parse_actions(text: str) -> list[int]:
    return [int(v) for v in text.split(",") if v.strip()]


def _parse_palettes(text: str) -> list[tuple[int, int]]:
    return [tuple(int(v) for v in entry.split(",")) for entry in text.split(";")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ikemen_sff")
    sub = ap.add_subparsers(dest="mode", required=True)

    char = sub.add_parser("char")
    char.add_argument("--sff", required=True)
    char.add_argument("--air", required=True)
    char.add_argument("--actions", type=_parse_actions, required=True,
                      help="comma-separated AIR action numbers")
    char.add_argument("--act-palettes", default=None,
                       help="semicolon-separated .act files used instead of "
                            "embedded SFF v1 palettes; first is the default")
    char.add_argument("--palettes", type=_parse_palettes, required=True,
                      help="palette (group,number) list, ';' separated; "
                           "first is main, others alt1..altN")
    char.add_argument("--out-prefix", required=True)
    char.add_argument("--symbol", required=True)
    char.add_argument("--sprite-bin",
                      help="packed runtime sprite payload binary output")
    char.add_argument("--png-dir")
    char.add_argument("--png-limit", type=int, default=8)
    char.set_defaults(fn=cmd_char)

    fx = sub.add_parser("fx")
    fx.add_argument("--sff", required=True)
    fx.add_argument("--air", required=True)
    fx.add_argument("--actions", type=_parse_actions, required=True,
                    help="comma-separated AIR action numbers")
    fx.add_argument("--out-prefix", required=True)
    fx.add_argument("--symbol", required=True)
    fx.add_argument("--sprite-bin",
                    help="packed runtime effect sprite payload binary output")
    fx.set_defaults(fn=cmd_fx)

    st = sub.add_parser("stage")
    st.add_argument("--sff", required=True)
    st.add_argument("--layers", required=True)
    st.add_argument("--out-prefix", required=True)
    st.add_argument("--symbol", required=True)
    st.add_argument("--png-dir")
    st.set_defaults(fn=cmd_stage)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
