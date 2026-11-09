"""Text decoding for legacy MUGEN character assets.

MUGEN character files in the original KOF source use UTF-8, Windows Japanese
code page 932, and single-byte Western encodings. Keep decoding centralized so
each asset compiler sees the same text instead of rejecting or dropping bytes.
"""
from __future__ import annotations

from pathlib import Path


def decode_mugen_text(data: bytes) -> str:
    """Decode text as UTF-8, CP932, CP1252, or Latin-1, in that order."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp932")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def read_mugen_text(path: str | Path) -> str:
    """Read a MUGEN text asset using the supported legacy encodings."""
    return decode_mugen_text(Path(path).read_bytes())
