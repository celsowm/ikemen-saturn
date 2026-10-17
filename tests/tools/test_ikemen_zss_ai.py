#!/usr/bin/env python3
"""Native ZSS AI must refuse source drift in the original State -1 branch."""
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.ikemen_zss_ai import EXPECTED, validate_ai_followup

source = Path(".external/Ikemen-GO-Screenpack/chars/kfm_zss/AI.zss")
validate_ai_followup(source)
assert EXPECTED.endswith("changestate{value:1075}}}")
with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    assert "moveContact && aiLevel < 6" in content
    changed = Path(temp) / "AI.zss"
    changed.write_text(
        content.replace("moveContact && aiLevel < 6",
                        "moveContact && aiLevel < 7", 1),
        encoding="utf-8")
    try:
        validate_ai_followup(changed)
    except ValueError as exc:
        assert "AI knee-followup source changed" in str(exc)
    else:
        raise AssertionError("unreviewed AI.zss clause accepted")
print("KFM ZSS AI knee follow-up source verified")
