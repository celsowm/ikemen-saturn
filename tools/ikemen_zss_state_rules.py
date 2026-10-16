#!/usr/bin/env python3
"""Compile the safely supported subset of ZSS State -1 to the Ikemen VM.

This is a strict State -1-only ZSS importer. It emits immediate
  if <predicate> { changeState{value: <constant>} }
branches. It does not interpret general ZSS statements, functions, AI,
side effects or nested controllers. Entries
that cannot be lowered are reported instead of silently approximated.

For human-controlled P2, the supported direct State -1 branches are executable.
AI script, general state bodies and MapControllers remain separate work.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from tools.ikemen_cmd import parse_cmd
from tools.ikemen_state_rules import Insn, Parser, Rule, emit

# In command.zss, Combo() is a pure predicate with a local return value:
# do not pretend the subsequent mapSet is a complete MapController port.
# Inline its exact conditions for the $canCombo references in attack rules.
COMBO = (
    "((stateType != A && ctrl) || "
    "((stateNo = [200, 299] || stateNo = [400, 499]) "
    "&& stateNo != 440 && moveContact) || "
    "(stateNo = 1310 || stateNo = 1330))"
)

# A ZSS if with exactly one immediate ChangeState controller, using a
# constant target. The brace-free condition guards against consuming a
# nested if/controller and accidentally changing the program's semantics.
BRANCH = re.compile(
    r"\bif\s+(?P<condition>[^{}]+?)\s*\{\s*"
    r"changeState\s*\{\s*value\s*:\s*(?P<target>-?\d+)\s*\}\s*\}",
    re.I | re.S,
)
CHANGE = re.compile(r"\bchangeState\s*\{", re.I)


def _without_comments(source: str) -> str:
    # '#' is the ZSS comment marker. Preserve quoted command literals.
    cleaned = []
    for line in source.splitlines():
        in_string = False
        escaped = False
        out = []
        for char in line:
            if char == '"' and not escaped:
                in_string = not in_string
            if char == "#" and not in_string:
                break
            out.append(char)
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
        cleaned.append("".join(out))
    return "\n".join(cleaned)


def compile_zss(path: Path, cmd: Path) -> tuple[list[Rule], list[str]]:
    text = _without_comments(path.read_text(encoding="utf-8-sig"))
    # Only the canonical command script is expected here. Never mix a
    # general ZSS StateDef (e.g. -4 AI or regular per-frame states) into
    # input-side ChangeState execution.
    statedef = re.findall(r"\[StateDef\s+(-?\d+)\s*\]", text, re.I)
    if statedef != ["-1"]:
        raise ValueError(f"{path}: expected only [StateDef -1], got {statedef}")

    names = parse_cmd(cmd).names
    command_ids = {name: i for i, name in enumerate(names)}
    rules: list[Rule] = []
    diagnostics: list[str] = []
    matches = list(BRANCH.finditer(text))
    if not matches:
        raise ValueError(f"{path}: no eligible ZSS ChangeState branches")

    for match in matches:
        target = int(match.group("target"))
        predicate = match.group("condition").strip()
        predicate = re.sub(r"\$canCombo\b", COMBO, predicate)
        try:
            # The entire ZSS State -1 command block is guarded by
            # roundState=2 and !aiLevelF in upstream. This partial import
            # supports human input; do not enable it for autonomous AI.
            code = Parser(predicate, command_ids).parse()
            code = [Insn("round_state_eq", 2), *code, Insn("and")]
        except ValueError as exc:
            diagnostics.append(f"state {target}: {exc}")
            continue
        rules.append(Rule(f"ZSS State -1 / ChangeState {target}", target, code))

    # Treat a newly added unsupported controller as visible diagnostic.
    # Do not claim this is a complete ZSS State -1 compiler.
    total_changes = len(CHANGE.findall(text))
    if total_changes > len(matches):
        diagnostics.append(
            f"{total_changes - len(matches)} ChangeState controller(s) "
            "outside immediately guarded constant-target branches")
    if len(rules) != len(matches):
        diagnostics.append(
            f"{len(matches) - len(rules)} direct branch(es) need VM expansion")
    # Do not silently deploy a truncated input program: for this known
    # source we require every direct ChangeState expression to compile.
    if diagnostics:
        raise ValueError(f"incomplete ZSS State -1 import: {diagnostics}")
    if not any(rule.target == 3050 for rule in rules):
        raise ValueError(f"{path}: Smash Kung Fu Upper not compiled")
    if not any(rule.target == 3000 for rule in rules):
        raise ValueError(f"{path}: Triple Kung Fu Palm not compiled")
    return rules, diagnostics


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--zss", required=True, type=Path)
    p.add_argument("--cmd", required=True, type=Path)
    p.add_argument("--out-prefix", required=True, type=Path)
    p.add_argument("--symbol", required=True)
    args = p.parse_args()
    rules, diagnostics = compile_zss(args.zss, args.cmd)
    emit(rules, diagnostics, args.out_prefix, args.symbol)
    print(f"[ikemen_zss_state_rules] {args.symbol}: "
          f"{len(rules)} supported entries, {len(diagnostics)} diagnostics "
          "(human input State -1 asset)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
