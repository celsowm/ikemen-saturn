#!/usr/bin/env python3
"""Compile the deterministic KFM CNS subset used by the Saturn runtime.

The Saturn never parses CNS text. This offline compiler emits:
* character constants ([Data]/[Size]/[Velocity]/[Movement]);
* selected Statedef metadata;
* HitDef and PlaySnd records;
* compact runtime controllers.

Unsupported controllers/triggers are reported instead of approximated.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
try:
    from .ikemen_cns_expr import (
        _ExprParser, character_name_hash,
        compile_cns_expr as compile_expression,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_expr import (
        _ExprParser, character_name_hash,
        compile_cns_expr as compile_expression,
    )
try:
    from .ikemen_cns_emit import emit_cns_source_files
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_emit import emit_cns_source_files
try:
    from .ikemen_cns_attributes import (
        attack_attr_mask, attack_state_mask, guard_mask, hit_mask,
        no_hit_by_attr_mask, no_hit_by_state_mask, priority_type_code,
        reversal_state_mask,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_attributes import (
        attack_attr_mask, attack_state_mask, guard_mask, hit_mask,
        no_hit_by_attr_mask, no_hit_by_state_mask, priority_type_code,
        reversal_state_mask,
    )
try:
    from .ikemen_cns_values import (
        Q8, anim_type_code, fall_anim_type_code, integer, number, pair,
        q8, q16, split_top_level as _split_top_level,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_values import (
        Q8, anim_type_code, fall_anim_type_code, integer, number, pair,
        q8, q16, split_top_level as _split_top_level,
    )
try:
    from .ikemen_cns_common import compile_common_states
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_common import compile_common_states
try:
    from .ikemen_cns_parse import Section, State, collect_states, parse_sections, select_state_numbers
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section, State, collect_states, parse_sections, select_state_numbers
try:
    from tools.ikemen_text import read_mugen_text
    from tools.ikemen_cmd import parse_cmd
except ModuleNotFoundError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_text import read_mugen_text
    from ikemen_cmd import parse_cmd

Q8 = 256
STRICT_CONVERSION = False
COMMAND_IDS: dict[str, int] = {}
LOCALCOORD_X = 320.0
CONST_VALUES: dict[str, float] = {}
CHARACTER_NAME_HASH = 0

STATE_TYPE = {
    "S": "IK_CNS_STATE_STAND",
    "C": "IK_CNS_STATE_CROUCH",
    "A": "IK_CNS_STATE_AIR",
    "L": "IK_CNS_STATE_LIEDOWN",
    "U": "IK_CNS_STATE_UNCHANGED",
}

MOVE_TYPE = {
    "I": "IK_CNS_MOVE_IDLE",
    "A": "IK_CNS_MOVE_ATTACK",
    "H": "IK_CNS_MOVE_HIT",
    "U": "IK_CNS_MOVE_UNCHANGED",
}

PHYSICS = {
    "N": "IK_CNS_PHYS_NONE",
    "S": "IK_CNS_PHYS_STAND",
    "C": "IK_CNS_PHYS_CROUCH",
    "A": "IK_CNS_PHYS_AIR",
    "U": "IK_CNS_PHYS_BY_TYPE",
}

GROUND_TYPE = {
    "normal": "IK_CNS_GROUND_NORMAL",
    "high": "IK_CNS_GROUND_HIGH",
    "low": "IK_CNS_GROUND_LOW",
    "trip": "IK_CNS_GROUND_TRIP",
}





def compile_cns_expr(text: str, q16: bool = False) -> list[dict]:
    return compile_expression(
        text,
        q16,
        command_ids=COMMAND_IDS,
        localcoord_x=LOCALCOORD_X,
        const_values=CONST_VALUES,
        self_anims=SELF_ANIMS,
    )


def integer_or_runtime_expr(
    text: str | None,
    default: int = 0,
) -> tuple[int, list[dict] | None]:
    if text is None or not text.strip():
        return default, None
    try:
        value = _ExprParser(text).parse()
        if int(value) != value:
            raise ValueError(f"expected integer expression, got {text!r}")
        return int(value), None
    except ValueError:
        try:
            code = compile_cns_expr(text)
        except ValueError:
            # MUGEN expressions can use real constants in integer-valued
            # fields such as PlaySnd group/item. Evaluate with Q16 precision,
            # then apply C/MUGEN-style truncation to the final value.
            try:
                code = compile_cns_expr(text, q16=True)
                code.append({"op": "IK_EXPR_TRUNC_Q16"})
            except ValueError as error:
                raise ValueError(
                    f"cannot compile integer expression {text!r}: {error}"
                ) from error
        return 0, code


def number_or_runtime_expr(
    text: str | None, default: float
) -> tuple[float, list[dict] | None]:
    if text is None:
        return default, None
    try:
        return number(text), None
    except ValueError:
        return default, compile_cns_expr(text, q16=True)


def pair_integer_runtime_expr(
    text: str | None,
    default_x: int = 0,
    default_y: int = 0,
) -> tuple[int, int, list[dict] | None, list[dict] | None]:
    if text is None:
        return default_x, default_y, None, None
    parts = _split_top_level(text)
    if len(parts) == 1:
        parts.append(str(default_y))
    if len(parts) not in (2, 3):
        raise ValueError(f"expected scalar or pair, got {text!r}")
    x, x_expr = integer_or_runtime_expr(parts[0], default_x)
    y, y_expr = integer_or_runtime_expr(parts[1], default_y)
    return x, y, x_expr, y_expr


def pair_runtime_expr(
    text: str | None,
    default_x: float = 0.0,
    default_y: float = 0.0,
) -> tuple[float, float, list[dict] | None, list[dict] | None]:
    if text is None or not text.strip():
        return default_x, default_y, None, None
    if SELF_ANIMS is not None:
        text = _SELF_ANIM_TERM.sub(
            lambda match: str(
                int(int(match.group(2)) in SELF_ANIMS) ^
                int(bool(match.group(1)))
            ),
            text,
        )
    parts = _split_top_level(text)
    if not parts or len(parts) > 3:
        raise ValueError(f"expected value pair, got {text!r}")
    if not parts[0].strip():
        parts[0] = str(default_x)
    if len(parts) > 1 and not parts[1].strip():
        parts[1] = str(default_y)
    if len(parts) == 3:
        # The Saturn fight simulation is a 2D plane. MUGEN permits a third
        # depth velocity component for 3D-style effects; it has no spatial
        # coordinate or collision counterpart in this runtime.
        parts.pop()
    if len(parts) == 1:
        parts.append(parts[0])
    values: list[float] = []
    expressions: list[list[dict] | None] = []
    for part, default in zip(parts, (default_x, default_y)):
        try:
            values.append(_ExprParser(part).parse())
            expressions.append(None)
        except ValueError:
            expressions.append(compile_cns_expr(part, q16=True))
            values.append(default)
    return values[0], values[1], expressions[0], expressions[1]


def compile_controller_trigger_expr(ctrl: Section) -> list[dict]:
    """Compile triggerall and triggerN lines with MUGEN's AND/OR grouping."""
    common = [f"({expr})" for expr in ctrl.all("triggerall")]
    groups: list[str] = []
    for index in range(1, 9):
        expressions = ctrl.all(f"trigger{index}")
        if not expressions:
            continue
        pieces = common + [f"({expr})" for expr in expressions]
        groups.append("(" + " && ".join(pieces) + ")")
    if not groups:
        raise ValueError(f"{ctrl.name}: missing trigger lines")
    return compile_cns_expr(" || ".join(groups), q16=True)


def eval_expr(text: str | None, default: float = 0.0) -> float:
    if text is None:
        return default
    text = text.strip()
    if not text:
        return default
    try:
        return _ExprParser(text).parse()
    except ValueError:
        if STRICT_CONVERSION:
            raise
        return default


def eval_int(text: str | None, default: int = 0) -> int:
    value = eval_expr(text, float(default))
    if int(value) != value:
        raise ValueError(f"expected integer expression, got {text!r}")
    return int(value)


def dynamic_power_add_expr(
    text: str | None,
    divisor: int = 1,
) -> list[dict] | None:
    """Compile a dynamic integer expression, optionally dividing its result."""
    if text is None:
        return None
    try:
        _ExprParser(text).parse()
        return None
    except ValueError:
        pass
    if divisor < 1:
        raise ValueError("dynamic expression divisor must be positive")
    try:
        code = compile_cns_expr(text)
    except ValueError as exc:
        if STRICT_CONVERSION:
            raise ValueError(f"unsupported dynamic integer expression {text!r}: {exc}") from exc
        return None
    if divisor != 1:
        code += [
            {"op": "IK_EXPR_PUSH_CONST", "value0": divisor},
            {"op": "IK_EXPR_DIV"},
        ]
    return code


def dist_fields(ctrl: Section) -> dict:
    """HitDef mindist / maxdist / snap = x[, y], in pixels. `snap` sets both
    limits. dist_flags: 1 mindist x, 2 mindist y, 4 maxdist x, 8 maxdist y."""
    out = {"mindist_x_q8": 0, "mindist_y_q8": 0, "maxdist_x_q8": 0,
           "maxdist_y_q8": 0, "dist_flags": 0}
    for key, names in (("mindist", ("min",)), ("maxdist", ("max",)),
                       ("snap", ("min", "max"))):
        text = ctrl.get(key)
        if text is None:
            continue
        parts = [p for p in _split_top_level(text) if p]
        for name in names:
            for axis, part in zip("xy", parts):
                out[f"{name}dist_{axis}_q8"] = q8(number(part))
                out["dist_flags"] |= {
                    ("min", "x"): 1, ("min", "y"): 2,
                    ("max", "x"): 4, ("max", "y"): 8}[(name, axis)]
    return out


def power_fields(ctrl: Section) -> dict:
    """HitDef getpower/givepower = hit[, guard]. An omitted guard value is
    half of the hit value (truncated toward zero); an absent key keeps the
    damage-based default (power_flags bit 0 = get set, bit 1 = give set)."""
    out = {"get_power_hit": 0, "get_power_guard": 0,
           "give_power_hit": 0, "give_power_guard": 0, "power_flags": 0}
    for key, name, bit in (("getpower", "get", 1), ("givepower", "give", 2)):
        text = ctrl.get(key)
        if text is None:
            continue
        parts = _split_top_level(text)
        hit_expr = dynamic_power_add_expr(parts[0])
        hit = 0 if hit_expr else integer(parts[0], 0)
        guard_text = parts[1] if len(parts) > 1 and parts[1] else None
        if guard_text is not None:
            guard_expr = dynamic_power_add_expr(guard_text)
            guard = 0 if guard_expr else integer(guard_text, 0)
        elif hit_expr is not None:
            guard_expr = dynamic_power_add_expr(parts[0], 2)
            guard = 0
        else:
            guard_expr = None
            guard = int(hit * 0.5)
        out[f"{name}_power_hit"] = hit
        out[f"{name}_power_guard"] = guard
        out[f"_{name}_power_hit_expr"] = hit_expr
        out[f"_{name}_power_guard_expr"] = guard_expr
        out["power_flags"] |= bit
    return out


def spark_pair(text: str | None) -> tuple[float, float, float]:
    if text is None:
        return 0.0, 0.0, 0.0
    parts = _split_top_level(text)
    if len(parts) == 1:
        return number(parts[0]), 0.0, 0.0
    if len(parts) != 2:
        raise ValueError(f"expected spark pair, got {text!r}")
    x = number(parts[0])
    try:
        y = number(parts[1])
        return x, y, y
    except ValueError:
        m = re.fullmatch(
            r"ifelse\s*\(\s*Time\s*=\s*0\s*,\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)",
            parts[1],
            flags=re.I,
        )
        if not m:
            raise
        return x, float(m.group(1)), float(m.group(2))


def spark_pair_runtime(text: str | None):
    """Compile sparkxy coordinates that are runtime CNS expressions."""
    if text is None:
        return 0, 0, 0, None, None, None
    parts = _split_top_level(text)
    if len(parts) not in (1, 2):
        raise ValueError(f"expected spark pair, got {text!r}")
    x, x_expr = integer_or_runtime_expr(parts[0], 0)
    if len(parts) == 1:
        return x, 0, 0, x_expr, None, None
    try:
        y, y2 = spark_pair("0," + parts[1])[1:]
        return x, int(y), int(y2), x_expr, None, None
    except ValueError:
        y, y_expr = integer_or_runtime_expr(parts[1], 0)
        return x, y, y, x_expr, y_expr, y_expr


def sound_pair(
    text: str | None,
    default: tuple[int, int] = (-1, -1),
) -> tuple[int, int]:
    if text is None:
        return default

    value = text.strip()
    if value[:1].lower() in ("s", "f"):
        value = value[1:]
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 1:
        return integer(parts[0]), -1
    if len(parts) != 2:
        raise ValueError(f"expected sound group,item, got {text!r}")
    return integer(parts[0]), integer(parts[1])


def sound_pair_runtime(text: str | None):
    if text is None:
        return -1, -1, None, None
    value = text.strip()
    if value[:1].lower() in ("s", "f"):
        value = value[1:]
    parts = _split_top_level(value)
    if len(parts) not in (1, 2):
        raise ValueError(f"expected sound group,item, got {text!r}")
    group, group_expr = integer_or_runtime_expr(parts[0], -1)
    if len(parts) == 1:
        return group, -1, group_expr, None
    item, item_expr = integer_or_runtime_expr(parts[1], -1)
    return group, item, group_expr, item_expr


def simple_trigger(section: Section) -> tuple[str, int, int]:
    triggers = section.all("trigger1")
    if not triggers:
        return "IK_CNS_TRIGGER_ALWAYS", 0, 0
    if len(triggers) != 1:
        raise ValueError(
            f"[{section.name}] unsupported trigger conjunction {triggers!r}"
        )

    expr = _strip_outer_parens(triggers[0].strip())

    if expr == "1":
        return "IK_CNS_TRIGGER_ALWAYS", 0, 0

    m = re.fullmatch(r"Time\s*=\s*(-?\d+)", expr, flags=re.I)
    if m:
        return "IK_CNS_TRIGGER_TIME_EQ", int(m.group(1)), 0

    m = re.fullmatch(r"AnimElem\s*=\s*(\d+)(?:,\s*=\s*(-?\d+))?", expr, flags=re.I)
    if m:
        elem = int(m.group(1))
        time = m.group(2)
        if time is not None:
            offset = int(time)
            if elem < 1 or elem > 255 or offset < -128 or offset > 127:
                raise ValueError(
                    f"[{section.name}] AnimElemTime packed trigger out of range"
                )
            packed = (elem << 8) | (offset & 0xff)
            if packed >= 32768:
                packed -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED", packed, 0
        return "IK_CNS_TRIGGER_ANIM_ELEM_EQ", elem, 0

    m = re.fullmatch(
        r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*=\s*(-?\d+)",
        expr,
        flags=re.I,
    )
    if m:
        elem = int(m.group(1))
        offset = int(m.group(2))
        if elem < 1 or elem > 255 or offset < -128 or offset > 127:
            raise ValueError(
                f"[{section.name}] AnimElemTime packed trigger out of range"
            )
        packed = (elem << 8) | (offset & 0xff)
        if packed >= 32768:
            packed -= 65536
        return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED", packed, 0

    if re.fullmatch(r"AnimTime\s*=\s*0", expr, flags=re.I):
        return "IK_CNS_TRIGGER_ANIM_END", 0, 0

    message = (
        f"[{section.name}] unsupported trigger expression {expr!r}; "
        "the converter will not replace it with an always-true trigger"
    )
    if STRICT_CONVERSION:
        raise ValueError(message)
    import sys
    print(f"[WARN] {message}; using compatibility fallback", file=sys.stderr)
    return "IK_CNS_TRIGGER_ALWAYS", 0, 0


def hitdef_trigger(
    section: Section,
) -> tuple[str, int, int, int, str, int, list[dict] | None, list[dict] | None]:
    triggers = section.all("trigger1") or ["1"]
    trigger2 = section.all("trigger2")
    trigger_all = section.all("triggerall")
    dist_op = "IK_CNS_P2_DIST_NONE"
    dist_value = 0

    def strip_distance(values: list[str]) -> list[str]:
        nonlocal dist_op, dist_value
        result = []
        for expr in values:
            value = _strip_outer_parens(expr)
            match = re.fullmatch(
                r"p2bodydist\s+X\s*(<|<=|>|>=)\s*(-?\d+)",
                value,
                flags=re.I,
            )
            if not match:
                result.append(expr)
                continue
            if dist_op != "IK_CNS_P2_DIST_NONE":
                raise ValueError(
                    f"[{section.name}] multiple p2bodydist predicates")
            dist_op = {
                "<": "IK_CNS_P2_DIST_LT",
                "<=": "IK_CNS_P2_DIST_LE",
                ">": "IK_CNS_P2_DIST_GT",
                ">=": "IK_CNS_P2_DIST_GE",
            }[match.group(1)]
            dist_value = int(match.group(2))
        return result

    def compile_group(values: list[str]) -> tuple[str, int, list[dict] | None]:
        if not values:
            return "IK_CNS_TRIGGER_ALWAYS", 0, None
        if len(values) == 1:
            expr = values[0]
            try:
                kind, value, _ = simple_trigger(
                    Section(section.name, [("trigger1", expr)]))
                if (kind != "IK_CNS_TRIGGER_ALWAYS" or
                        expr.strip().casefold() in {"1", "1.0", "true"}):
                    return kind, value, None
            except ValueError:
                if not STRICT_CONVERSION:
                    raise
        conjunction = " && ".join(f"({expr})" for expr in values)
        try:
            code = compile_cns_expr(conjunction, q16=True)
        except ValueError as exc:
            raise ValueError(
                f"[{section.name}] unsupported HitDef trigger conjunction "
                f"{conjunction!r}: {exc}") from exc
        return "IK_CNS_TRIGGER_ALWAYS", 0, code

    primary_values = strip_distance([*trigger_all, *triggers])
    if not primary_values:
        primary_values = ["1"]
    base, base_value, base_expr = compile_group(primary_values)

    second_kind = 255
    second_value = 0
    second_expr: list[dict] | None = None
    if trigger2:
        secondary_values = strip_distance([*trigger_all, *trigger2])
        if not secondary_values:
            secondary_values = ["1"]
        second_kind, second_value, second_expr = compile_group(secondary_values)

    return (
        base or "IK_CNS_TRIGGER_ALWAYS",
        base_value,
        second_kind,
        second_value,
        dist_op,
        dist_value,
        base_expr,
        second_expr,
    )


def _strip_outer_parens(text: str) -> str:
    value = text.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        balanced = True
        for i, ch in enumerate(value):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(value) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        value = value[1:-1].strip()
    return value


def _anim_elem_range_trigger(expr: str) -> tuple[int, int] | None:
    value = _strip_outer_parens(expr)
    pattern = re.compile(
        r"^\(?\s*AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*0\s*\)?"
        r"\s*&&\s*"
        r"\(?\s*AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0\s*\)?$",
        flags=re.I,
    )
    m = pattern.fullmatch(value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _move_contact_window(
    triggers: list[str],
) -> tuple[int, int] | None:
    if len(triggers) != 2:
        return None

    normalized = [_strip_outer_parens(t) for t in triggers]
    if not any(re.fullmatch(r"movecontact", t, flags=re.I) for t in normalized):
        return None

    window = next(
        (
            t
            for t in normalized
            if not re.fullmatch(r"movecontact", t, flags=re.I)
        ),
        None,
    )
    if window is None:
        return None

    pattern = re.compile(
        r"^\(?\s*AnimElemTime\s*\(\s*(\d+)\s*\)\s*>\s*0\s*\)?"
        r"\s*&&\s*"
        r"\(?\s*AnimElemTime\s*\(\s*(\d+)\s*\)\s*<=\s*0\s*\)?$",
        flags=re.I,
    )
    m = pattern.fullmatch(window)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# Action numbers of the character's .air file (--air). SelfAnimExist(n) is
# resolved against it while compiling: a character's action set is fixed.
SELF_ANIMS: set[int] | None = None

_SELF_ANIM_TERM = re.compile(
    r"(!?)\s*SelfAnimExist\s*\(\s*(\d+)\s*\)", re.I)


def load_air_actions(path: Path) -> set[int]:
    text = read_mugen_text(path)
    return {
        int(m.group(1))
        for m in re.finditer(r"^\s*\[Begin Action\s+(\d+)\s*\]", text,
                             re.I | re.M)
    }



def fold_self_anim_exist(ctrl: Section) -> Section | None:
    """Resolve `SelfAnimExist(n)` terms that make up a whole trigger line.
    A true term is dropped (an otherwise empty group becomes `1`); a false
    one kills its triggerN group, or the whole controller for triggerall.
    Returns None when the controller can never fire."""
    if SELF_ANIMS is None or not any(
            _SELF_ANIM_TERM.fullmatch(v.strip()) for k, v in ctrl.values
            if k.lower().startswith("trigger")):
        return ctrl
    groups: dict[str, list[tuple[str, str]]] = {}
    other: list[tuple[str, str]] = []
    dead: set[str] = set()
    for key, value in ctrl.values:
        k = key.lower()
        if not k.startswith("trigger"):
            other.append((key, value))
            continue
        groups.setdefault(k, [])
        m = _SELF_ANIM_TERM.fullmatch(value.strip())
        if m is None:
            groups[k].append((key, value))
        elif (int(m.group(2)) in SELF_ANIMS) == (m.group(1) != "!"):
            continue                      # true: the term drops out
        elif k == "triggerall":
            return None
        else:
            dead.add(k)
    values = list(other)
    live = 0
    for k, lines in groups.items():
        if k in dead:
            continue
        if k != "triggerall":
            live += 1
        values.extend(lines or [(k, "1")])
    if live == 0:
        return None
    return Section(ctrl.name, values)


def controller_trigger(
    ctrl: Section,
    ctype: str,
) -> tuple[str, int, int]:
    return _cns_triggers.compile_controller_trigger(
        ctrl, ctype, services=globals())


def constants(globals_: dict[str, Section]) -> dict[str, int]:
    data = globals_.get("data", Section("Data"))
    size = globals_.get("size", Section("Size"))
    vel = globals_.get("velocity", Section("Velocity"))
    movement = globals_.get("movement", Section("Movement"))

    run_fwd = pair(vel.get("run.fwd"))
    run_back = pair(vel.get("run.back"))
    jump_neu = pair(vel.get("jump.neu"))
    jump_back = pair(vel.get("jump.back"), -2.55)[0]
    jump_fwd = pair(vel.get("jump.fwd"), 2.5)[0]
    run_jump_fwd = pair(vel.get("runjump.fwd"), 4.0, -8.1)
    air_jump_neu = pair(vel.get("airjump.neu"), 0.0, -8.1)
    air_jump_back = pair(vel.get("airjump.back"), -2.55)[0]
    air_jump_fwd = pair(vel.get("airjump.fwd"), 2.5)[0]
    ground_recover = pair(vel.get("air.gethit.groundrecover"), -.15, -3.5)
    air_recover_mul = pair(vel.get("air.gethit.airrecover.mul"), .5, .2)
    air_recover_add = pair(vel.get("air.gethit.airrecover.add"), 0, -4.5)
    air_ko_add = pair(vel.get("air.gethit.ko.add"), -2.5, -2.0)
    ground_ko_add = pair(vel.get("ground.gethit.ko.add"), -2.5, -2.0)

    return {
        "life": integer(data.get("life"), 1000),
        "air_juggle": integer(data.get("airjuggle"), 15),
        # HitDef values inherit these [Data] defaults when omitted.
        # They are compiler-only metadata; ik_cns_constants_t stays unchanged.
        "default_spark_no": integer(data.get("sparkno"), 2),
        "default_guard_spark_no": integer(data.get("guard.sparkno"), 40),
        "ground_back": integer(size.get("ground.back"), 15),
        "ground_front": integer(size.get("ground.front"), 16),
        "air_back": integer(size.get("air.back"), 12),
        "air_front": integer(size.get("air.front"), 12),
        "height": integer(size.get("height"), 60),
        "attack_dist": integer(size.get("attack.dist"), 160),
        "head_pos_x": int(pair(size.get("head.pos"), 0, 0)[0]),
        "head_pos_y": int(pair(size.get("head.pos"), 0, 0)[1]),
        "mid_pos_x": int(pair(size.get("mid.pos"), 0, 0)[0]),
        "mid_pos_y": int(pair(size.get("mid.pos"), 0, 0)[1]),
        "walk_fwd_q8": q8(number(vel.get("walk.fwd"), 2.4)),
        "walk_back_q8": q8(number(vel.get("walk.back"), -2.2)),
        "run_fwd_x_q8": q8(run_fwd[0]),
        "run_fwd_y_q8": q8(run_fwd[1]),
        "run_back_x_q8": q8(run_back[0]),
        "run_back_y_q8": q8(run_back[1]),
        "jump_neu_x_q8": q8(jump_neu[0]),
        "jump_neu_y_q8": q8(jump_neu[1]),
        "jump_back_q8": q8(jump_back),
        "jump_fwd_q8": q8(jump_fwd),
        "run_jump_fwd_x_q8": q8(run_jump_fwd[0]),
        "run_jump_fwd_y_q8": q8(run_jump_fwd[1]),
        "air_jump_neu_x_q8": q8(air_jump_neu[0]),
        "air_jump_neu_y_q8": q8(air_jump_neu[1]),
        "air_jump_back_q8": q8(air_jump_back),
        "air_jump_fwd_q8": q8(air_jump_fwd),
        "air_jump_num": integer(movement.get("airjump.num"), 0),
        "air_jump_height": integer(movement.get("airjump.height"), 35),
        "yaccel_q8": q8(
            number(movement.get("yaccel"), .44) * 320.0 / LOCALCOORD_X),
        "yaccel_q16": q16(
            number(movement.get("yaccel"), .44) * 320.0 / LOCALCOORD_X),
        "stand_friction_q16": q16(
            number(movement.get("stand.friction"), .85)),
        "crouch_friction_q16": q16(
            number(movement.get("crouch.friction"), .82)),
        "air_gethit_airrecover_yaccel_q16": q16(
            number(movement.get("air.gethit.airrecover.yaccel"), .35)),
        "stand_friction_q8": q8(number(movement.get("stand.friction"), .85)),
        "crouch_friction_q8": q8(number(movement.get("crouch.friction"), .82)),
        "stand_friction_threshold_q8": q8(
            number(movement.get("stand.friction.threshold"), 2.0)
        ),
        "crouch_friction_threshold_q8": q8(
            number(movement.get("crouch.friction.threshold"), .05)
        ),
        "liedown_time": integer(data.get("liedown.time"), 60),
        "air_gethit_groundlevel_q8": q8(
            number(movement.get("air.gethit.groundlevel"), 25)
        ),
        "air_gethit_trip_groundlevel_q8": q8(
            number(movement.get("air.gethit.trip.groundlevel"), 15)
        ),
        "down_bounce_offset_x_q8": q8(
            pair(movement.get("down.bounce.offset"), 0, 20)[0]
        ),
        "down_bounce_offset_y_q8": q8(
            pair(movement.get("down.bounce.offset"), 0, 20)[1]
        ),
        "down_bounce_yaccel_q8": q8(
            number(movement.get("down.bounce.yaccel"), .4)
        ),
        "down_bounce_groundlevel_q8": q8(
            number(movement.get("down.bounce.groundlevel"), 12)
        ),
        "down_friction_threshold_q8": q8(
            number(movement.get("down.friction.threshold"), .05)
        ),
        "air_gethit_groundrecover_x_q8": q8(ground_recover[0]),
        "air_gethit_groundrecover_y_q8": q8(ground_recover[1]),
        "air_gethit_groundrecover_threshold_q8": q8(
            number(
                movement.get("air.gethit.groundrecover.ground.threshold"),
                -20,
            )
        ),
        "air_gethit_groundrecover_groundlevel_q8": q8(
            number(movement.get("air.gethit.groundrecover.groundlevel"), 10)
        ),
        "air_gethit_airrecover_mul_x_q8": q8(air_recover_mul[0]),
        "air_gethit_airrecover_mul_y_q8": q8(air_recover_mul[1]),
        "air_gethit_airrecover_add_x_q8": q8(air_recover_add[0]),
        "air_gethit_airrecover_add_y_q8": q8(air_recover_add[1]),
        "air_gethit_airrecover_back_q8": q8(
            number(vel.get("air.gethit.airrecover.back"), -1)
        ),
        "air_gethit_airrecover_fwd_q8": q8(
            number(vel.get("air.gethit.airrecover.fwd"), 0)
        ),
        "air_gethit_airrecover_up_q8": q8(
            number(vel.get("air.gethit.airrecover.up"), -2)
        ),
        "air_gethit_airrecover_down_q8": q8(
            number(vel.get("air.gethit.airrecover.down"), 1.5)
        ),
        "air_gethit_airrecover_threshold_q8": q8(
            number(movement.get("air.gethit.airrecover.threshold"), -1)
        ),
        "air_gethit_airrecover_yaccel_q8": q8(
            number(movement.get("air.gethit.airrecover.yaccel"), .35)
        ),
        "air_gethit_ko_add_x_q8": q8(air_ko_add[0]),
        "air_gethit_ko_add_y_q8": q8(air_ko_add[1]),
        "air_gethit_ko_ymin_q8": q8(
            number(vel.get("air.gethit.ko.ymin"), -3.0)
        ),
        "ground_gethit_ko_xmul_q16": q16(
            number(vel.get("ground.gethit.ko.xmul"), .66)
        ),
        "ground_gethit_ko_add_x_q8": q8(ground_ko_add[0]),
        "ground_gethit_ko_add_y_q8": q8(ground_ko_add[1]),
        "ground_gethit_ko_ymin_q8": q8(
            number(vel.get("ground.gethit.ko.ymin"), -6.0)
        ),
    }


try:
    from . import ikemen_cns_triggers as _cns_triggers
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    import ikemen_cns_triggers as _cns_triggers


try:
    from . import ikemen_cns_controllers as _cns_controllers
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    import ikemen_cns_controllers as _cns_controllers


def compile_runtime_controller(state_no: int, ctrl: Section) -> dict | None:
    return _cns_controllers.compile_runtime_controller(state_no, ctrl, services=globals())

def compile_helper_controller(state_no: int, ctrl: Section, helper_index: int) -> tuple[dict, dict] | None:
    return _cns_controllers.compile_helper_controller(state_no, ctrl, helper_index, services=globals())

def guard_times(ctrl: Section) -> tuple[int, int, int]:
    return _cns_controllers.guard_times(ctrl, services=globals())

def guard_times_runtime(ctrl: Section, ground_slide: int, ground_slide_expr: list[dict] | None) -> tuple[tuple[int, int, int], tuple[list[dict] | None, ...]]:
    return _cns_controllers.guard_times_runtime(ctrl, ground_slide, ground_slide_expr, services=globals())

def _projectile_hitdef_row(state_no: int, ctrl: Section, default_spark_no: int, default_guard_spark_no: int) -> dict:
    return _cns_controllers._projectile_hitdef_row(state_no, ctrl, default_spark_no, default_guard_spark_no, services=globals())

def compile_projectile_controller(state_no: int, ctrl: Section, projectile_index: int, hitdef_global: int, default_spark_no: int, default_guard_spark_no: int) -> tuple[dict, dict, dict] | None:
    return _cns_controllers.compile_projectile_controller(state_no, ctrl, projectile_index, hitdef_global, default_spark_no, default_guard_spark_no, services=globals())

def compile_modify_projectile_controller(state_no: int, ctrl: Section, mod_index: int) -> tuple[dict, dict] | None:
    return _cns_controllers.compile_modify_projectile_controller(state_no, ctrl, mod_index, services=globals())

def compile_explod_controller(state_no: int, ctrl: Section, explod_index: int) -> tuple[dict, dict] | None:
    return _cns_controllers.compile_explod_controller(state_no, ctrl, explod_index, services=globals())




try:
    from .ikemen_cns_state import compile_state
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_state import compile_state


def parse_state(
    state: State,
    hitdef_ofs: int,
    sound_ofs: int,
    controller_ofs: int,
    helper_ofs: int,
    explod_ofs: int,
    projectile_ofs: int,
    projectile_mod_ofs: int,
    default_spark_no: int = -1,
    default_guard_spark_no: int = 40,
):
    return compile_state(
        state,
        hitdef_ofs,
        sound_ofs,
        controller_ofs,
        helper_ofs,
        explod_ofs,
        projectile_ofs,
        projectile_mod_ofs,
        default_spark_no,
        default_guard_spark_no,
        services=globals(),
    )




def emit(
    path: Path,
    selected: list[int],
    out_prefix: Path,
    symbol: str,
    common_zss: Path | None = None,
    common_selected: list[int] | None = None,
    constants_source: Path | None = None,
    character_zss: Path | None = None,
    hits_zss: Path | None = None,
    states_sources: list[Path] | None = None,
) -> dict:
    state_sections = parse_sections(path)
    for source in states_sources or []:
        state_sections.extend(parse_sections(source))
    globals_, states = collect_states(state_sections)
    by_number = {state.number: state for state in states}

    # Ikemen ZSS characters can keep [Data]/[Size]/[Velocity]/[Movement]
    # in a separate .const file. Until their ZSS state bodies are lowered,
    # permit a distinct source for constants without substituting defaults.
    const_globals = globals_
    if constants_source is not None:
        const_globals, _ = collect_states(parse_sections(constants_source))
        required = {"data", "size", "velocity", "movement"}
        missing = required - set(const_globals)
        if missing:
            raise ValueError(
                f"{constants_source}: missing constants sections: {sorted(missing)}")
    const = constants(const_globals)
    const["character_name_hash"] = CHARACTER_NAME_HASH
    global CONST_VALUES
    CONST_VALUES = {}
    for section_name in ("data", "size", "velocity", "movement"):
        section = const_globals.get(section_name)
        if section is None:
            continue
        for key, value in section.values:
            try:
                parts = _split_top_level(value)
                values = [_ExprParser(part).parse() for part in parts]
            except ValueError:
                continue
            prefix = f"{section_name}.{key.casefold()}"
            if section_name == "velocity":
                scale = 320.0 / LOCALCOORD_X
                values = [value * scale for value in values]
            elif section_name == "movement" and (
                key.casefold() == "yaccel" or
                key.casefold().endswith(".threshold") or
                key.casefold().endswith(".yaccel")
            ):
                values = [value * 320.0 / LOCALCOORD_X for value in values]
            CONST_VALUES[prefix] = values[0]
            if section_name == "velocity":
                # Ikemen exposes velocity constants as named components even
                # when the CNS declaration uses a scalar (for example,
                # walk.fwd -> velocity.walk.fwd.x).
                CONST_VALUES[f"{prefix}.x"] = values[0]
                if len(values) > 1:
                    CONST_VALUES[f"{prefix}.y"] = values[1]
                if len(values) > 2:
                    CONST_VALUES[f"{prefix}.z"] = values[2]
                if key.casefold() in {"jump.neu", "airjump.neu"} and len(values) > 1:
                    CONST_VALUES[f"velocity.{key.split('.')[0].casefold()}.y"] = values[1]
                if key.casefold() == "runjump.fwd" and len(values) > 1:
                    CONST_VALUES["velocity.runjump.y"] = values[1]
    CONST_VALUES.setdefault(
        "movement.stand.friction.threshold",
        2.0 * 320.0 / LOCALCOORD_X)
    CONST_VALUES.setdefault("movement.crouch.friction.threshold", 0.0)
    # Only strict, source-checked ZSS states are admitted. Every other P2
    # state deliberately keeps its original classic-CNS compatibility path.
    zss_overrides = {}
    if character_zss is not None or hits_zss is not None:
        if character_zss is None or hits_zss is None:
            raise ValueError("character-zss and hits-zss must be provided together")
        from tools.ikemen_zss_character_states import (compile_zss_overrides,
                                                      zss_row_patch)
        zss_overrides = compile_zss_overrides(character_zss, hits_zss, const)
        from tools.ikemen_zss_ai import (validate_ai_followup,
                                          validate_ai_neutral,
                                          validate_ai_combat)
        ai_source = character_zss.with_name("AI.zss")
        validate_ai_followup(ai_source)
        validate_ai_neutral(ai_source)
        validate_ai_combat(ai_source)
        outside = sorted(set(zss_overrides) - set(selected))
        if outside:
            raise ValueError(f"ZSS override states not selected: {outside}")
    # A selected number may be absent from the classic CNS as long as a
    # source-checked ZSS body supplies it (the ZSS character file owns its
    # own walk/run states, which classic KFM inherits from common1).
    missing = [n for n in selected
               if n not in by_number and n not in zss_overrides]
    if missing:
        raise ValueError(f"missing Statedef(s): {missing}")
    state_rows: list[dict] = []
    hitdefs: list[dict] = []
    sounds: list[dict] = []
    controllers: list[dict] = []
    helpers: list[dict] = []
    explods: list[dict] = []
    projectiles: list[dict] = []
    projectile_mods: list[dict] = []
    reversals: list[dict] = []
    hitoverrides: list[dict] = []

    for number_ in selected:
        zss_override = zss_overrides.get(number_)
        source_state = zss_override[0] if zss_override else by_number[number_]
        (
            row, hs, ss, cs, helper_rows, explod_rows,
            projectile_rows, projectile_mod_rows,
            reversal_rows, hitoverride_rows
        ) = parse_state(
            source_state,
            len(hitdefs),
            len(sounds),
            len(controllers),
            len(helpers),
            len(explods),
            len(projectiles),
            len(projectile_mods),
            const["default_spark_no"],
            const["default_guard_spark_no"],
        )
        if zss_override is not None:
            if zss_override[1] and (hs or ss or cs or helper_rows or explod_rows or projectile_rows):
                raise ValueError(
                    f"state {number_}: unexpected duplicate ZSS controllers")
            # ZSS bodies are lowered as native CNS controllers with exactly
            # the offsets used by classic states and common1.zss.
            # Source-checked bodies may need state-row fields their StateDef
            # omits (walk/run ctrl, static assert flags). The patch values are
            # fixed by the verified shared locomotion lowering, not invented
            # per character.
            row.update(zss_row_patch(number_))
            if zss_override[1]:
                cs = list(zss_override[1])
                row["controller_count"] = len(cs)
                row["owns_air_accel"] = int(any(
                    c["type"] == "IK_CNS_CTRL_VEL_ADD" and
                    "IK_CNS_CTRL_AXIS_Y" in c["flags"] for c in cs))
            elif number_ in (200, 210, 230, 240, 400, 410, 430, 440, 1000, 1010, 1020, 1100, 1110, 1120, 1200, 1210, 1220, 1400, 1410, 1420):
                endings = [c for c in cs if c["type"] == "IK_CNS_CTRL_CHANGE_STATE"
                           and c["trigger_kind"] == "IK_CNS_TRIGGER_ANIM_END"]
                if len(endings) != 1:
                    raise ValueError(f"state {number_}: missing verified EndState")
                endings[0]["flags"] = "IK_CNS_CTRL_HAS_CTRL | IK_CNS_CTRL_CTRL_FROM_ROUND"
            row["source"] = "zss"
        else:
            row["source"] = "classic_cns"
        row["reversal_ofs"] = len(reversals)
        row["hitoverride_ofs"] = len(hitoverrides)
        state_rows.append(row)
        hitdefs.extend(hs)
        sounds.extend(ss)
        controllers.extend(cs)
        helpers.extend(helper_rows)
        explods.extend(explod_rows)
        projectiles.extend(projectile_rows)
        projectile_mods.extend(projectile_mod_rows)
        reversals.extend(reversal_rows)
        hitoverrides.extend(hitoverride_rows)

    common_deferred: dict[int, list[str]] = {}
    # A source-checked ZSS body supersedes the common1 fallback for the same
    # number; emitting both would duplicate the row without changing lookup
    # (first match wins), so the shadowed common rows are dropped.
    common_effective = [n for n in (common_selected or [])
                        if n not in zss_overrides]
    if common_zss is not None and common_effective:
        common_rows, common_ctrls, common_deferred = compile_common_states(
            common_zss, common_effective, const, len(controllers),
            STATE_TYPE, MOVE_TYPE, PHYSICS,
        )
        state_rows.extend(common_rows)
        controllers.extend(common_ctrls)

    emit_cns_source_files(
        out_prefix, symbol, const, state_rows, hitdefs, sounds, controllers,
        helpers, explods, projectiles, projectile_mods, reversals, hitoverrides,
    )

    report = {
        "states": state_rows,
        "constants": const,
        "hitdefs": hitdefs,
        "playsnds": sounds,
        "controllers": controllers,
        "helpers": helpers,
        "explods": explods,
        "projectiles": projectiles,
        "projectile_mods": projectile_mods,
        "reversals": reversals,
        "hitoverrides": hitoverrides,
        "common_deferred": common_deferred,
    }
    out_prefix.with_suffix(".json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cns", required=True, type=Path)
    parser.add_argument("--character-def", type=Path,
                        help="character DEF used to read Info.localcoord")
    parser.add_argument("--constants-cns", type=Path,
                        help="separate [Data]/[Size]/[Velocity]/[Movement] file")
    parser.add_argument("--character-zss", type=Path,
                        help="original ZSS character states (strict subset)")
    parser.add_argument("--hits-zss", type=Path,
                        help="original ZSS hit reactions (strict subset)")
    parser.add_argument(
        "--states", default="all",
        help="comma-separated Statedef numbers, or 'all' (default)",
    )
    parser.add_argument(
        "--states-source", action="append", type=Path, default=[],
        help="additional CNS/ST file referenced by the character DEF",
    )
    parser.add_argument(
        "--command-source", action="append", type=Path, default=[],
        help="CMD file used to resolve command trigger IDs",
    )
    parser.add_argument("--common-zss", type=Path)
    parser.add_argument("--air", type=Path,
                        help="the character's .air file (SelfAnimExist)")
    parser.add_argument("--common-states", default="")
    parser.add_argument(
        "--strict", action="store_true",
        help="fail on unsupported triggers or deferred controllers")
    parser.add_argument("--out-prefix", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args(argv)

    global STRICT_CONVERSION
    STRICT_CONVERSION = args.strict

    global COMMAND_IDS
    COMMAND_IDS = {}
    for command_source in args.command_source:
        for command in parse_cmd(command_source).names:
            key = command.casefold()
            if key not in COMMAND_IDS:
                COMMAND_IDS[key] = len(COMMAND_IDS)
    if len(COMMAND_IDS) > 128:
        raise ValueError("CNS command table exceeds the 128-name expression limit")

    global LOCALCOORD_X, CHARACTER_NAME_HASH
    LOCALCOORD_X = 320.0
    CHARACTER_NAME_HASH = 0
    if args.character_def is not None:
        def_text = read_mugen_text(args.character_def)
        section = ""
        for raw in def_text.splitlines():
            line = raw.split(";", 1)[0].strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().casefold()
            elif section == "info" and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().casefold()
                if key == "name":
                    CHARACTER_NAME_HASH = character_name_hash(
                        value.strip().strip('"'))
                elif key == "localcoord":
                    parts = _split_top_level(value)
                    if not parts or number(parts[0]) <= 0:
                        raise ValueError(
                            f"{args.character_def}: invalid localcoord {value!r}")
                    LOCALCOORD_X = number(parts[0])

    global SELF_ANIMS
    if args.air is not None:
        SELF_ANIMS = load_air_actions(args.air)

    selected = select_state_numbers(
        args.states, [args.cns, *args.states_source])

    common_selected = [
        int(value.strip())
        for value in args.common_states.split(",")
        if value.strip()
    ]

    report = emit(
        args.cns,
        selected,
        args.out_prefix,
        args.symbol,
        args.common_zss,
        common_selected,
        args.constants_cns,
        args.character_zss,
        args.hits_zss,
        args.states_source,
    )

    unsupported = {
        row["number"]: row["unsupported_controllers"]
        for row in report["states"]
        if row["unsupported_controllers"]
    }

    print(
        f"[ikemen_cns] {args.symbol}: "
        f"states={len(report['states'])} "
        f"hitdefs={len(report['hitdefs'])} "
        f"playsnds={len(report['playsnds'])} "
        f"controllers={len(report['controllers'])} "
        f"helpers={len(report['helpers'])} "
        f"explods={len(report['explods'])} "
        f"projectiles={len(report['projectiles'])} "
        f"projectile_mods={len(report['projectile_mods'])} "
        f"reversals={len(report['reversals'])} "
        f"hitoverrides={len(report['hitoverrides'])}"
    )

    if unsupported:
        print(f"[ikemen_cns] deferred controllers: {unsupported}")
        if args.strict:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
