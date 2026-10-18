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

# These *selected* original AI.zss clauses are guarded against source drift.
# They do not constitute a translation of the entire neutral AI loop.
NEUTRAL_CLAUSES = [
    'ifstatetype=s&&ctrl&&stateno!=100&&random<249&&(p2movetype!=a||backedgebodydist<40)&&p2bodydistx=[25,120]&&map(aiw)!=0{changestate{value:20}}',
    'ifmap(aiw)=0&&stateno=20{printtoconsole{text:"changestate{value:0}"}changestate{value:0;ctrl:1}}',
    'ifstatetype!=a&&(ctrl||stateno=20)&&stateno!=100&&random<=(396*(ailevelf**2/48.0))&&(p2movetype!=a||backedgebodydist<40)&&(p2bodydistx>=cond($hitfall||p2stateno=5300,10,120)){changestate{value:100}}',
    'ifstateno=100&&(p2bodydistx<40-20*(!$grounded)&&p2stateno!=5040||p2bodydistx<-65||roundstate!=2){changestate{value:0;ctrl:1}}',
    'letatt=cond(p2bodydisty<-40||p2statetype=s,200,400);'
]


def validate_ai_neutral(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    for clause in NEUTRAL_CLAUSES:
        if compact.count(clause) != 1:
            raise ValueError(
                f"{path}: ZSS AI neutral source changed at {clause[:45]!r}; "
                "refusing stale movement/attack slice")
