"""Pixel codec strategies for SFF v2 sprite data.

Each codec is a callable taking (data, width, height) and returning
row-major 8bpp palette indices. New formats plug in through CODECS
without touching callers (open/closed). Decoders are direct ports of
Ikemen GO's src/image.go (Rle8Decode / Rle5Decode / Lz5Decode); the
"advance unless at the final byte" cursor behaviour is preserved so
trailing bytes stay unconsumed exactly like the original reader.
"""
from __future__ import annotations

import io
import struct

from . import sff

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("ikemen_sff requires Pillow for PNG sprites") from exc


class UnsupportedCodec(ValueError):
    def __init__(self, fmt: int):
        super().__init__(f"unsupported SFF pixel format {fmt}")


def _decode_raw(data: bytes, width: int, height: int) -> bytes:
    if len(data) < width * height:
        raise ValueError("raw sprite shorter than w*h")
    return data[:width * height]


def _decode_rle8(data: bytes, width: int, height: int) -> bytes:
    # Container prefixes 4 bytes of metadata before the RLE stream.
    rle = data[4:]
    out = bytearray(width * height)
    if not rle:
        return bytes(out)
    i = j = 0
    while j < len(out):
        count, value = 1, rle[i]
        if i < len(rle) - 1:
            i += 1
        if value & 0xC0 == 0x40:
            count = value & 0x3F
            value = rle[i]
            if i < len(rle) - 1:
                i += 1
        while count > 0 and j < len(out):
            out[j] = value
            j += 1
            count -= 1
    return bytes(out)


def _decode_rle5(data: bytes, width: int, height: int) -> bytes:
    rle = data[4:]
    out = bytearray(width * height)
    if not rle:
        return bytes(out)
    i = j = 0
    while j < len(out):
        run_length = rle[i]
        if i < len(rle) - 1:
            i += 1
        delta_length = rle[i] & 0x7F
        color = 0
        if rle[i] >> 7:
            if i < len(rle) - 1:
                i += 1
            color = rle[i]
        if i < len(rle) - 1:
            i += 1
        while True:
            if j < len(out):
                out[j] = color
                j += 1
            run_length -= 1
            if run_length < 0:
                delta_length -= 1
                if delta_length < 0:
                    break
                color = rle[i] & 0x1F
                run_length = rle[i] >> 5
                if i < len(rle) - 1:
                    i += 1
    return bytes(out)


def _decode_lz5(data: bytes, width: int, height: int) -> bytes:
    src = data[4:]
    out = bytearray(width * height)
    if not src:
        return bytes(out)
    i = j = n = 0
    control, cts, rebuilt, rbc = src[i], 0, 0, 0
    if i < len(src) - 1:
        i += 1
    while j < len(out):
        d = src[i]
        if i < len(src) - 1:
            i += 1
        if control & (1 << cts):
            # Back-reference: n copies of out[j-d].
            if d & 0x3F == 0:
                d = ((d << 2) | src[i]) + 1
                if i < len(src) - 1:
                    i += 1
                n = src[i] + 2
                if i < len(src) - 1:
                    i += 1
            else:
                # Go's '&' and '>>' have the same precedence and evaluate
                # left-to-right: Ikemen's "d & 0xc0 >> rbc" means this.
                rebuilt |= (d & 0xC0) >> rbc
                rbc += 2
                n = d & 0x3F
                if rbc < 8:
                    d = src[i] + 1
                    if i < len(src) - 1:
                        i += 1
                else:
                    d = rebuilt + 1
                    rebuilt, rbc = 0, 0
            while True:
                if j < len(out):
                    out[j] = out[j - d]
                    j += 1
                n -= 1
                if n < 0:
                    break
        else:
            # Literal run: n copies of the 5-bit color d & 0x1F.
            if d & 0xE0 == 0:
                n = src[i] + 8
                if i < len(src) - 1:
                    i += 1
            else:
                n = d >> 5
                d &= 0x1F
            while n > 0:
                if j < len(out):
                    out[j] = d & 0xFF
                    j += 1
                n -= 1
        cts += 1
        if cts >= 8:
            control = src[i]
            cts = 0
            if i < len(src) - 1:
                i += 1
    return bytes(out)


def _decode_png_indexed(data: bytes, width: int, height: int) -> bytes:
    # PNG streams carry the same 4-byte prefix as the RLE codecs
    # (Ikemen seeks offset+4 before png.Decode).
    img = Image.open(io.BytesIO(data[4:]))
    if img.mode != "P":
        raise UnsupportedCodec(10 if img.mode == "P" else -10)
    indices = img.tobytes()
    if len(indices) < width * height:
        raise ValueError("PNG indexed sprite shorter than w*h")
    return indices[:width * height]


def pcx_palette_offset(data: bytes) -> int | None:
    """Offset of the 768-byte VGA palette block, or None when absent.

    Every SFF v1 PCX carries a palette either as the last 768 bytes of the
    sprite payload (character's first sprite) or behind a 0x0C marker just
    before them (regular sprites). The RLE pixel stream stops where the
    palette begins.
    """
    if len(data) >= 769 and data[-769] == 0x0C:
        return len(data) - 768
    if len(data) >= 768:
        return len(data) - 768
    return None


def _decode_pcx(data: bytes, width: int, height: int) -> bytes:
    # PCX layout: 128-byte header, then the pixel stream, then optional
    # 0x0C marker + 768-byte palette at the end.
    if len(data) < 128:
        raise ValueError("PCX sprite shorter than header")
    palette_offset = pcx_palette_offset(data)
    stream_end = palette_offset if palette_offset is not None else len(data)
    encoding = data[2]
    bytes_per_line = struct.unpack_from("<H", data, 66)[0]
    if bytes_per_line <= 0:
        bytes_per_line = width
    out = bytearray(width * height)
    if encoding != 1:
        # Uncompressed: raw bytes per row, right-padded to bytes_per_line.
        pos = 128
        for y in range(height):
            row = data[pos:pos + bytes_per_line]
            pos += bytes_per_line
            start = y * width
            out[start:start + width] = row[:width]
        return bytes(out)
    rle = data[128:stream_end]
    # Faithful port of Ikemen-GO RlePcxDecode: every bytes_per_line *decoded*
    # bytes close the current row; pixels past `width` in a row are dropped
    # and the run remainder is discarded.
    i = 0
    j = 0
    k = 0
    while j < len(out):
        if i >= len(rle):
            break
        n = 1
        d = rle[i]
        i += 1
        if d >= 0xC0:
            n = d & 0x3F
            if i >= len(rle):
                break
            d = rle[i]
            i += 1
        while n > 0 and j < len(out):
            if k < width:
                out[j] = d
                j += 1
            k += 1
            n -= 1
            if k == bytes_per_line:
                k = 0
                break
    return bytes(out)


CODECS = {
    sff.FORMAT_RAW: _decode_raw,
    sff.FORMAT_RLE8: _decode_rle8,
    sff.FORMAT_RLE5: _decode_rle5,
    sff.FORMAT_LZ5: _decode_lz5,
    sff.FORMAT_PNG_INDEXED: _decode_png_indexed,
    sff.FORMAT_PCX: _decode_pcx,
}


def decode(node: sff.SpriteNode, data: bytes) -> bytes:
    """Decodes sprite data into w*h palette indices (strategy dispatch)."""
    if node.fmt in (sff.FORMAT_PNG_RGBA, sff.FORMAT_PNG_RGBA2):
        raise UnsupportedCodec(node.fmt)
    codec = CODECS.get(node.fmt)
    if codec is None:
        raise UnsupportedCodec(node.fmt)
    return codec(data, node.width, node.height)
