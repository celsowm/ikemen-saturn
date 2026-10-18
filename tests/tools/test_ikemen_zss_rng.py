#!/usr/bin/env python3
"""Pin authentic upstream Go Random()/Rand() and bytecode random trigger."""
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.ikemen_zss_ai import validate_go_rng

root = Path(".external/Ikemen-GO/src")
validate_go_rng(root / "common.go", root / "bytecode.go")
with TemporaryDirectory() as temp:
    bad = Path(temp) / "common.go"
    original = (root / "common.go").read_text(encoding="utf-8")
    assert "16807" in original
    bad.write_text(original.replace("*16807", "*16809", 1), encoding="utf-8")
    try:
        validate_go_rng(bad, root / "bytecode.go")
    except ValueError as exc:
        assert "upstream Random/Rand changed" in str(exc)
    else:
        raise AssertionError("unreviewed Go RNG multiplier accepted")
    bad_bc = Path(temp) / "bytecode.go"
    bytecode = (root / "bytecode.go").read_text(encoding="utf-8")
    assert "sys.bcStack.PushI(Rand(0, 999))" in bytecode
    bad_bc.write_text(
        bytecode.replace("sys.bcStack.PushI(Rand(0, 999))",
                         "sys.bcStack.PushI(Random() % 1000)", 1),
        encoding="utf-8",
    )
    try:
        validate_go_rng(root / "common.go", bad_bc)
    except ValueError as exc:
        assert "upstream random trigger changed" in str(exc)
    else:
        raise AssertionError("modulo random falsely accepted as GO trigger")
print("pinned upstream RNG and OC_random source contracts OK")
