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
    'letatt=cond(p2bodydisty<-40||p2statetype=s,200,400);',
    # The real GO trace attributed 56 draws to the close throw expression.
    'ifrandom<=(310*(ailevelf**2/48.0))&&statetype=s&&stateno!=100&&(p2movetype!=h||p2stateno=[120,131])&&(map(ai_ji)<2)&&p2bodydistx<30&&$grounded{changestate{value:800}}',
    'ifp2bodydistx<60+(floor($trvelx*.4)*5)&&!$ai_ji&&(!$nojug||p2bodydisty>-10)&&(!map(gurt)||p2bodydistx>35)&&random<=(425*(ailevelf**2/48.0))&&(p2stateno!=[1025,1028]||p2movetype!=h)',
]


# Pinned original State -1 jump declaration and cancellation fragments.
# The native lowering deliberately accepts only the conservative neutral
# 80..90px case and does not claim the complete AIJ/gurt/AI_JI state machine.
MEMORY_CLAUSES = [
    'ifanim=5120||roundstate!=2{mapset{map:"gurt";value:10}}',
    'ifctrl&&!p2,ctrl&&(p2,gethitvar(hittime)>0){letai_ji=p2,gethitvar(hittime);}',
    'ifmap(gurt)>0{mapadd{map:"gurt";value:-1}}',
    'letaiJ=1;',
    'letaiJ=0;',
    '||$ai_ji>0{mapset{map:"aiw";value:1}}',
]


def validate_ai_memory(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    for clause in MEMORY_CLAUSES:
        if compact.count(clause.lower()) != 1:
            raise ValueError(
                f"{path}: ZSS AI memory source changed at {clause[:50]!r}; "
                "refusing stale native AI bookkeeping")


JUMP_CLAUSES = [
    'ifstatetype!=a&&(((!map(gurt))&&(random<(375*(ailevelf**2/48.0))||p2movetype=a&&ailevelf>6)',
    '(p2bodydistx=[70,90+(floor(velx*.4)*5)]||frontedgedist<30)&&p2movetype!=h',
    'p2bodydistx<80&&frontedgebodydist>60&&!$nojug',
    'if$aij&&(ctrl||stateno=20||stateno=100){changestate{value:40}}',
]


def validate_ai_jump(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    for clause in JUMP_CLAUSES:
        if compact.count(clause) != 1:
            raise ValueError(
                f"{path}: ZSS AI jump source changed at {clause[:48]!r}; "
                "refusing stale native jumping rule")


def validate_ai_neutral(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    for clause in NEUTRAL_CLAUSES:
        if compact.count(clause) != 1:
            raise ValueError(
                f"{path}: ZSS AI neutral source changed at {clause[:45]!r}; "
                "refusing stale movement/attack slice")


# Validate exact source predicates that the bounded combat slice is based on.
# Guards are not claims of whole-body ZSS / random-stream parity.
COMBAT_CLAUSES = [
    'ifp2bodydistx=[-15,30+floor($trvelx*.4)*10+floor(p2,const(size.attack.dist)*.5)]&&p2bodydisty=[-50+(floor(p2,vely*.6)*-10),0]&&random<=(335*(ailevelf**2/48.0))&&p2movetype=a&&ailevel>4{changestate{value:cond(p2statetype!=c,1300,1320)}}',
    'if(p2movetype=a&&prevstateno!=[1300,1350]&&stateno!=[1300,1350]&&inguarddist&&random<=(700*(ailevelf**2/48.0))',
    'ifp2statetype=a&&p2bodydistx=[5*($hitfall)-20,(30+floor($trvelx*.4)*20)]',
    'ifpower>=500&&p2,alive&&random%3=1{letversion=1120;',
    '}elseifmovecontact=[1,3]&&hitpausetime=0&&statetype!=a{',
    'ifp2bodydistx<85&&movehit&&$lights&&!$nojug&&random<(600*(ailevelf**2/48.0))',
    'if($heavy||$lights&&(!$grounded&&p2bodydisty<-10&p2bodydistx>55||p2bodydistx>55))&&(movehit)&&($hitfall||$grounded||$cc>11)&&random<(800*(ailevelf**2/48.0))',
    'if($sc||($heavy&&(p2,life<350)||$lights))&&movehit&&jugglepoints(p2,id)>1&&random<(700*(ailevelf**2/48.0))'
]


def validate_ai_combat(path: Path) -> None:
    source = path.read_text(encoding="utf-8-sig")
    compact = "".join(line.split("#", 1)[0] for line in source.splitlines())
    compact = re.sub(r"\s+", "", compact).lower()
    for clause in COMBAT_CLAUSES:
        if compact.count(clause) != 1:
            raise ValueError(
                f"{path}: ZSS AI combat source changed at {clause[:48]!r}; "
                "refusing stale native defensive/cancel decisions")


# The native decision stream uses these *exact* pinned Go RNG primitives.
# This guard detects source changes; it does not assert game-wide call parity.
def validate_go_rng(common_go: Path, bytecode_go: Path) -> None:
    common = common_go.read_text(encoding="utf-8")
    bytecode = bytecode_go.read_text(encoding="utf-8")
    # A local GO oracle checkout may be instrumented by install.py.
    # Discard only fenced oracle-owned source injections when verifying the
    # unchanged original Random()/Rand()/OC_random definitions.
    oracle_block = re.compile(
        r"^[ \t]*// LIBSATURN_ORACLE_BEGIN\n"
        r".*?^[ \t]*// LIBSATURN_ORACLE_END\n",
        flags=re.MULTILINE | re.DOTALL,
    )
    common = oracle_block.sub("", common)
    bytecode = oracle_block.sub("", bytecode)
    expected = (
        "w := sys.randseed / 127773",
        "sys.randseed = (sys.randseed-w*127773)*16807 - w*2836",
        "if sys.randseed <= 0 {",
        "sys.randseed += IMax - Btoi(sys.randseed == 0)",
        "return min + Random()/(IMax/(max-min+1)+1)",
    )
    compact = re.sub(r"\s+", "", common)
    for clause in expected:
        if re.sub(r"\s+", "", clause) not in compact:
            raise ValueError(f"{common_go}: upstream Random/Rand changed at {clause!r}")
    if re.search(
        r"case\s+OC_random\s*:\s*sys\.bcStack\.PushI\(Rand\(0,\s*999\)\)",
        bytecode,
    ) is None:
        raise ValueError(f"{bytecode_go}: upstream random trigger changed")
