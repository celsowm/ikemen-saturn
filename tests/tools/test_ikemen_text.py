#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_text import decode_mugen_text, read_mugen_text  # noqa: E402

assert decode_mugen_text(b"\xef\xbb\xbfname=Kyo") == "name=Kyo"
assert decode_mugen_text("name=Kyo café".encode("utf-8")) == "name=Kyo café"
assert decode_mugen_text("name=Kyo 日本語".encode("cp932")) == "name=Kyo 日本語"
assert decode_mugen_text(b"name=Andr\xe9") == "name=André"
assert decode_mugen_text(b"name=\x92quoted\x92") == "name=’quoted’"

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "legacy.cmd"
    path.write_bytes(b"[Command]\nname=Kyo\ncommand=x ; Ren\xe9\n")
    assert "René" in read_mugen_text(path)

print("ikemen legacy MUGEN text decoding: OK")
