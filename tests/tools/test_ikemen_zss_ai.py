#!/usr/bin/env python3
"""Native ZSS AI must refuse source drift in the original State -1 branch."""
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.ikemen_zss_ai import (EXPECTED, validate_ai_followup,
                                 validate_ai_neutral, validate_ai_combat,
                                 validate_ai_jump, validate_ai_memory,
                                 validate_ai_poke)

source = Path(".external/Ikemen-GO-Screenpack/chars/kfm_zss/AI.zss")
validate_ai_followup(source)
validate_ai_neutral(source)
validate_ai_combat(source)
validate_ai_jump(source)
validate_ai_memory(source)
validate_ai_poke(source)
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

with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    for old, new in (
        ("random <= (396 * (aiLevelF ** 2 / 48.0))",
         "random <= (397 * (aiLevelF ** 2 / 48.0))"),
        ("p2BodyDist x = [25, 120]", "p2BodyDist x = [25, 125]"),
        ("if map(AIw) = 0 && stateNo = 20",
         "if map(AIw) = 1 && stateNo = 20"),
        ("random <= (310 * (aiLevelF ** 2 / 48.0))",
         "random <= (311 * (aiLevelF ** 2 / 48.0))"),
        ("random <= (425 * (aiLevelF ** 2 / 48.0))",
         "random <= (426 * (aiLevelF ** 2 / 48.0))"),
    ):
        assert old in content
        changed = Path(temp) / "AI.zss"
        changed.write_text(content.replace(old, new, 1), encoding="utf-8")
        try:
            validate_ai_neutral(changed)
        except ValueError as exc:
            assert "ZSS AI neutral source changed" in str(exc)
        else:
            raise AssertionError(f"AI source drift accepted: {old}")
print("KFM ZSS AI neutral source guards OK")

with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    for old, new in (
        ("random <= (335 * (aiLevelF ** 2 / 48.0))",
         "random <= (336 * (aiLevelF ** 2 / 48.0))"),
        ("moveContact = [1, 3]", "moveContact = [1, 4]"),
        ("let version = 1120;", "let version = 1121;"),
    ):
        assert old in content
        changed = Path(temp) / "AI.zss"
        changed.write_text(content.replace(old, new, 1), encoding="utf-8")
        try:
            validate_ai_combat(changed)
        except ValueError as exc:
            assert "ZSS AI combat source changed" in str(exc)
        else:
            raise AssertionError(f"AI combat source drift missed: {old}")
print("KFM ZSS AI combat source guards OK")

with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    for old, new in (
        ("random < (375 * (aiLevelF ** 2 / 48.0))",
         "random < (376 * (aiLevelF ** 2 / 48.0))"),
        ("if $AIJ && (ctrl || stateNo = 20 || stateNo = 100)",
         "if $AIJ && (ctrl || stateNo = 20 || stateNo = 99)"),
        ("p2BodyDist x < 80 && frontEdgeBodyDist > 60 && !$nojug",
         "p2BodyDist x < 81 && frontEdgeBodyDist > 60 && !$nojug"),
    ):
        assert old in content
        changed = Path(temp) / "AI.zss"
        changed.write_text(content.replace(old, new, 1), encoding="utf-8")
        try:
            validate_ai_jump(changed)
        except ValueError as exc:
            assert "ZSS AI jump source changed" in str(exc)
        else:
            raise AssertionError(f"unreviewed jumping rule accepted: {old}")
print("KFM ZSS AI jump source guards OK")

with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    for old, new in (
        ('mapSet{map: "gurt"; value: 10}', 'mapSet{map: "gurt"; value: 11}'),
        ('mapAdd{map: "gurt"; value: -1}', 'mapAdd{map: "gurt"; value: -2}'),
        ('let AI_JI = p2,getHitVar(hittime);',
         'let AI_JI = p2,getHitVar(fall.recovertime);'),
    ):
        assert old in content
        changed = Path(temp) / "AI.zss"
        changed.write_text(content.replace(old, new, 1), encoding="utf-8")
        try:
            validate_ai_memory(changed)
        except ValueError as exc:
            assert "ZSS AI memory source changed" in str(exc)
        else:
            raise AssertionError(f"AI memory drift accepted: {old}")
print("KFM ZSS AI per-frame and persistent memory source guards OK")

with TemporaryDirectory() as temp:
    content = source.read_text(encoding="utf-8-sig")
    for old, new in (
        ('random < (250 * (aiLevelF ** 2 / 48.0))',
         'random < (251 * (aiLevelF ** 2 / 48.0))'),
        ('random%4 = 0', 'random%4 = 2'),
        ('random%4 = 1', 'random%4 = 3'),
        ('p2BodyDist x < 45 + (floor($trvelx * .4) * 5)',
         'p2BodyDist x < 46 + (floor($trvelx * .4) * 5)'),
    ):
        assert old in content
        modified = Path(temp) / "AI.zss"
        modified.write_text(content.replace(old, new, 1), encoding="utf-8")
        try:
            validate_ai_poke(modified)
        except ValueError as exc:
            assert "ZSS AI poke source changed" in str(exc)
        else:
            raise AssertionError(f"unsafe source drift accepted: {old}")
print("KFM ZSS AI medium-range poke source guards OK")
