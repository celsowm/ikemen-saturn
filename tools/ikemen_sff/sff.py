"""SFF v2 container parsing (no pixel decoding here; see codecs.py).

Layout follows Ikemen GO's reader (src/image.go, SffHeader.Read /
readHeaderV2 / loadPalettes), which is the authoritative consumer of the
screenpack files this pipeline targets.

Header (64 bytes):
  0-11   "ElecbyteSpr\\0"
  12-15  version bytes (lo3..., verhi last; verhi==2 selects v2)
  16-19  reserved
  20-35  reserved x4
  36-39  first sprite node offset
  40-43  number of sprites
  44-47  first palette node offset
  48-51  number of palettes
  52-55  lofs (sprite/palette data base offset)
  56-59  reserved
  60-63  tofs (second data base, selected by node flag bit 0)

Sprite node (28 bytes, sequential): group u16, number u16, w u16, h u16,
xoff i16, yoff i16, palette link u16, format u8, color depth u8,
data offset u32, data length u32, palette index u16, flags u16.

Palette node (16 bytes): group u16, number u16, colors u16, link u16,
data offset u32, data size u32 (RGBA quads, 4 bytes per entry).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

SIGNATURE = b"ElecbyteSpr\x00"
HEADER_SIZE = 64
SPRITE_NODE_SIZE = 28
PALETTE_NODE_SIZE = 16

FORMAT_RAW = 0
FORMAT_RLE8 = 2
FORMAT_RLE5 = 3
FORMAT_LZ5 = 4
FORMAT_PNG_INDEXED = 10
FORMAT_PNG_RGBA = 11
FORMAT_PNG_RGBA2 = 12
FORMAT_PCX = 5  # SFF v1 PCX sprite payload


class SffFormatError(ValueError):
    """Raised when a file is not a supported SFF v2 container."""


@dataclass(frozen=True)
class SpriteNode:
    group: int
    number: int
    width: int
    height: int
    xoff: int
    yoff: int
    palette_link: int
    fmt: int
    coldepth: int
    data_offset: int
    data_length: int
    palette_index: int
    flags: int
    # SFF v1 only: byte 18 of the node header. Non-zero means the sprite
    # shares the palette of the previous sprite in the file list
    # (Ikemen-GO read(): paletteSame). Always 0 for v2 nodes.
    ps: int = 0


@dataclass(frozen=True)
class PaletteNode:
    group: int
    number: int
    colors: int
    link: int
    data_offset: int
    data_size: int


@dataclass
class SffContainer:
    data: bytes
    first_sprite_offset: int
    sprite_count: int
    first_palette_offset: int
    palette_count: int
    lofs: int
    tofs: int
    version: int = 2

    def sprite_nodes(self):
        if self.version == 1:
            shofs = self.first_sprite_offset
            for i in range(self.sprite_count):
                if shofs + 18 > len(self.data):
                    break
                ofs, size, xoff, yoff, group, number, link = struct.unpack_from(
                    '<IIhhHHH', self.data, shofs)
                ps = self.data[shofs + 18]
                pcx_offset = shofs + 32
                width = 1
                height = 1
                fmt = FORMAT_PCX
                if pcx_offset + 128 <= len(self.data):
                    xmin, ymin, xmax, ymax = struct.unpack_from(
                        '<hhhh', self.data, pcx_offset + 4)
                    width = max(1, xmax - xmin + 1)
                    height = max(1, ymax - ymin + 1)
                    encoding = self.data[pcx_offset + 2]
                    if encoding == 0:
                        fmt = FORMAT_RAW
                    else:
                        fmt = FORMAT_PCX
                yield SpriteNode(
                    group=group,
                    number=number,
                    width=width,
                    height=height,
                    xoff=xoff,
                    yoff=yoff,
                    palette_link=link,
                    fmt=fmt,
                    coldepth=8,
                    data_offset=pcx_offset,
                    data_length=size,
                    palette_index=0,
                    flags=0,
                    ps=ps,
                )
                shofs = ofs
                # SFF v1 placeholders carry size == 0 and share the pixels of
                # the sprite at list index `link` (see Ikemen-GO readHeader /
                # image.go). They are not end-of-list markers; the list only
                # ends when the next offset is zero.
                if ofs == 0:
                    break
            return
        for i in range(self.sprite_count):
            base = self.first_sprite_offset + i * SPRITE_NODE_SIZE
            if base + SPRITE_NODE_SIZE > len(self.data):
                break
            (group, number, w, h, xoff, yoff, link, fmt, depth,
             ofs, length, palidx, flags) = struct.unpack_from(
                "<HHHHhhHBBIIHH", self.data, base)
            yield SpriteNode(group, number, w, h, xoff, yoff, link, fmt,
                             depth, ofs, length, palidx, flags)

    def sprite_data(self, node: SpriteNode) -> bytes:
        if self.version == 1:
            start = node.data_offset
        else:
            base = self.tofs if (node.flags & 1) else self.lofs
            start = base + node.data_offset
        if node.data_length == 0:
            return b""
        end = start + node.data_length
        if end > len(self.data):
            end = len(self.data)
        return self.data[start:end]

    def palette_nodes(self):
        if self.version == 1:
            return
        for i in range(self.palette_count):
            base = self.first_palette_offset + i * PALETTE_NODE_SIZE
            if base + PALETTE_NODE_SIZE > len(self.data):
                break
            group, number, colors, link, ofs, size = struct.unpack_from(
                "<HHHHII", self.data, base)
            yield PaletteNode(group, number, colors, link, ofs, size)

    def palette_data(self, node: PaletteNode) -> bytes:
        if self.version == 1:
            raise SffFormatError("SFF v1 has no separate palette nodes")
        if node.data_size == 0:
            return b""
        start = self.lofs + node.data_offset
        if start + node.data_size > len(self.data):
            return self.data[start:]
        return self.data[start:start + node.data_size]

    def palette_by_index(self, index: int) -> PaletteNode:
        if self.version == 1:
            raise SffFormatError("SFF v1 has no palette index table")
        for i, node in enumerate(self.palette_nodes()):
            if i == index:
                return node
        raise SffFormatError(f"palette index {index} out of range")


def load(path: Path) -> SffContainer:
    data = Path(path).read_bytes()
    if len(data) < HEADER_SIZE or not data.startswith(SIGNATURE):
        raise SffFormatError(f"{path}: not an SFF file")
    verhi = data[15]
    if verhi == 2:
        (first_sprite, sprite_count, first_palette, palette_count,
         lofs, _reserved, tofs) = struct.unpack_from("<7I", data, 36)
        return SffContainer(data, first_sprite, sprite_count,
                            first_palette, palette_count, lofs, tofs,
                            version=2)
    if verhi == 1:
        sprite_count = struct.unpack_from("<I", data, 20)[0]
        first_sprite = struct.unpack_from("<I", data, 24)[0]
        return SffContainer(data, first_sprite, sprite_count,
                            0, 0, 0, 0, version=1)
    raise SffFormatError(
        f"{path}: SFF v{verhi} not supported (v1 and v2 only)")
