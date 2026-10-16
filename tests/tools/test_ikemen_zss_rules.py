#!/usr/bin/env python3
"""Source-driven ZSS rule compiler smoke tests (no false parity claims)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ikemen_zss_state_rules import compile_zss  # noqa: E402
from tools.ikemen_state_rules import emit  # noqa: E402

base = ROOT / ".external" / "Ikemen-GO-Screenpack" / "chars" / "kfm_zss"
rules, diagnostics = compile_zss(base / "command.zss", base / "kfm.cmd")
targets = [r.target for r in rules]

# These entries must be sourced from upstream ZSS rather than generated
# from classic kfm.cmd; failures mean the importer silently lost a move.
for state in (3050, 3000, 1070, 1120, 1420, 1020, 1220,
              1050, 1060, 1100, 1110, 1400, 1410, 1000, 1010,
              1200, 1210, 1300, 1320, 1340, 100, 105, 800, 195, 400,
              200, 210, 230, 240, 410, 430, 440, 600, 610, 630, 640):
    assert state in targets, f"missing supported ZSS command for state {state}"
assert len(rules) == len(set(targets)), "unexpected duplicate State -1 targets"
assert not diagnostics, f"incomplete ZSS input rule import: {diagnostics}"
assert len(rules) == 36, f"expected all 36 authored ZSS ChangeState branches, got {len(rules)}"
assert all(r.code[0].op == "round_state_eq" for r in rules)

with tempfile.TemporaryDirectory() as temp:
    prefix = Path(temp) / "zss_rules"
    emit(rules, diagnostics, prefix, "test_zss")
    report = json.loads(prefix.with_suffix(".json").read_text())
    header = prefix.with_suffix(".h").read_text()
    source = prefix.with_suffix(".c").read_text()
    assert report["targets"] == targets
    assert report["rule_count"] == len(rules)
    assert "IK_EXPR_FIELD_ROUND_STATE" in source
    assert "IK_EXPR_FIELD_ANIM_ELEM_TIME" in source
    assert "TEST_ZSS_STATE_RULE_COUNT" in header
    assert report["diagnostics"] == diagnostics

print(f"ZSS partial State -1 compilation: {len(rules)} entries, "
      f"{len(diagnostics)} diagnostics (human State -1 complete)")
