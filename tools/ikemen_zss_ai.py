#!/usr/bin/env python3
"""Fail closed when the one lowered AI.zss State -1 branch changes."""
from __future__ import annotations
import re
from pathlib import Path

EXPECTED = ('if(stateno=1051||stateno=1061||stateno=1071)'
            '&&(movehit||movecontact&&ailevel<6)&&vely<-1'
            '{ifstateno=[1050,1069]{changestate{value:1055}}'
            'else{changestate{value:1075}}}')


def validate_ai_followup(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    if compact.count(EXPECTED) != 1:
        raise ValueError(f"{path}: ZSS AI knee-followup source changed; "
                         "refusing stale native AI branch")
