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


def number(text: str | None, default: float = 0.0) -> float:
    if text is None:
        return default
    value = text.strip()
    # MUGEN allows string references like s4000 for sparkno/guard.sparkno.
    if value[:1].casefold() == "s":
        value = value[1:]
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise ValueError(f"expected numeric literal, got {text!r}")
    return float(value)


def integer(text: str | None, default: int = 0) -> int:
    value = number(text, float(default))
    if int(value) != value:
        raise ValueError(f"expected integer literal, got {text!r}")
    return int(value)


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            redirect_prefix = re.search(
                r"\b(?:parent|root|p2|enemy)\s*$",
                text[start:i], re.I,
            )
            redirected_field = re.match(
                r"\s*(?:var|sysvar|fvar|pos|vel|stateno|statetype|movetype)\b",
                text[i + 1:], re.I,
            )
            if redirect_prefix and redirected_field:
                continue
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return parts


def pair(
    text: str | None,
    default_x: float = 0.0,
    default_y: float = 0.0,
) -> tuple[float, float]:
    if text is None:
        return default_x, default_y

    parts = _split_top_level(text)
    if len(parts) == 1:
        return number(parts[0]), default_y
    if len(parts) == 2 or len(parts) == 3:
        return number(parts[0]), number(parts[1])
    raise ValueError(f"expected scalar or pair, got {text!r}")


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


def q8(value: float, wide: bool = False) -> int:
    """Q8.8 fixed point; `wide` is for fields stored as int32 in the asset."""
    result = int(round(value * Q8))
    low, high = (-(1 << 31), (1 << 31) - 1) if wide else (-32768, 32767)
    if not low <= result <= high:
        raise ValueError(f"Q8.8 overflow for {value}")
    return result


def q16(value: float) -> int:
    """Q16.16 for the few constants whose Q8.8 rounding drifts a fighter
    (gravity and friction accumulate every tick)."""
    result = int(round(value * 65536))
    if not -(1 << 31) <= result < (1 << 31):
        raise ValueError(f"Q16.16 overflow for {value}")
    return result


def anim_type_code(text: str | None) -> int:
    value = (text or "light").strip().lower()
    mapping = {
        "light": 0,
        "medium": 1,
        "med": 1,
        "hard": 2,
        "heavy": 2,
        "back": 3,
        "up": 4,
        "diagup": 5,
        "diag-up": 5,
    }
    return mapping.get(value, 0)


def fall_anim_type_code(ctrl: dict) -> int:
    """Upstream: explicit fall.animtype, else air.animtype if it is Up or
    DiagUp, else Back."""
    if ctrl.get("fall.animtype") is not None:
        return anim_type_code(ctrl.get("fall.animtype"))
    air = anim_type_code(
        ctrl.get("air.animtype") or ctrl.get("animtype") or "light")
    return air if air >= 4 else 3


def attack_attr_mask(text: str | None) -> str:
    value = (text or "").strip().upper()
    mapping = {
        "NA": "IK_CNS_ATTR_NORMAL_ATTACK",
        "SA": "IK_CNS_ATTR_SPECIAL_ATTACK",
        "HA": "IK_CNS_ATTR_HYPER_ATTACK",
        "NP": "IK_CNS_ATTR_NORMAL_PROJECTILE",
        "SP": "IK_CNS_ATTR_SPECIAL_PROJECTILE",
        "HP": "IK_CNS_ATTR_HYPER_PROJECTILE",
        "NT": "IK_CNS_ATTR_NORMAL_THROW",
        "ST": "IK_CNS_ATTR_SPECIAL_THROW",
        "HT": "IK_CNS_ATTR_HYPER_THROW",
    }
    if value == "AP":
        return (
            "IK_CNS_ATTR_NORMAL_PROJECTILE | "
            "IK_CNS_ATTR_SPECIAL_PROJECTILE | "
            "IK_CNS_ATTR_HYPER_PROJECTILE"
        )
    if value == "AA":
        return (
            "IK_CNS_ATTR_NORMAL_ATTACK | "
            "IK_CNS_ATTR_SPECIAL_ATTACK | "
            "IK_CNS_ATTR_HYPER_ATTACK"
        )
    if value == "AT":
        return (
            "IK_CNS_ATTR_NORMAL_THROW | "
            "IK_CNS_ATTR_SPECIAL_THROW | "
            "IK_CNS_ATTR_HYPER_THROW"
        )
    bits = [
        mapping[token]
        for token in re.split(r"\s+", value)
        if token in mapping
    ]
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def priority_type_code(text: str | None) -> str:
    value = (text or "4, Hit").split(",", 1)
    kind = value[1].strip().lower() if len(value) > 1 else "hit"
    if kind in ("miss", "m"):
        return "IK_CNS_PRIORITY_MISS"
    if kind in ("dodge", "d"):
        return "IK_CNS_PRIORITY_DODGE"
    return "IK_CNS_PRIORITY_HIT"


def guard_mask(text: str | None) -> str:
    value = (text or "").strip().upper()
    bits: list[str] = []
    if "H" in value:
        bits.append("IK_CNS_GUARD_STAND")
    if "L" in value:
        bits.append("IK_CNS_GUARD_CROUCH")
    if "M" in value:
        bits += ["IK_CNS_GUARD_STAND", "IK_CNS_GUARD_CROUCH"]
    if "A" in value:
        bits.append("IK_CNS_GUARD_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def no_hit_by_state_mask(text: str | None) -> str:
    value = (text or "").split(",", 1)[0].strip().upper()
    if value == "":
        return (
            "IK_CNS_REVERSAL_STATE_STAND | "
            "IK_CNS_REVERSAL_STATE_CROUCH | "
            "IK_CNS_REVERSAL_STATE_AIR"
        )
    bits: list[str] = []
    if "S" in value:
        bits.append("IK_CNS_REVERSAL_STATE_STAND")
    if "C" in value:
        bits.append("IK_CNS_REVERSAL_STATE_CROUCH")
    if "A" in value:
        bits.append("IK_CNS_REVERSAL_STATE_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def no_hit_by_attr_mask(text: str | None) -> str:
    parts = [p.strip().upper() for p in (text or "").split(",")]
    if len(parts) <= 1:
        return "0u"
    bits: list[str] = []
    for token in parts[1:]:
        if token == "AT":
            bits.extend([
                "IK_CNS_ATTR_NORMAL_THROW",
                "IK_CNS_ATTR_SPECIAL_THROW",
                "IK_CNS_ATTR_HYPER_THROW",
            ])
            continue
        mask = attack_attr_mask(token)
        if mask != "0u":
            bits.extend(part.strip() for part in mask.split("|"))
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def reversal_state_mask(text: str | None) -> str:
    """Compile the state-type half of ReversalDef.attr.

    ReversalDef uses the first attr field to select the attacker's state
    type. KFM's Blocking family uses SA, C and A with AA (any attack) as the
    second field, so keep the runtime representation deliberately compact.
    """
    value = (text or "").strip().upper()
    bits: list[str] = []
    if "S" in value:
        bits.append("IK_CNS_REVERSAL_STATE_STAND")
    if "C" in value:
        bits.append("IK_CNS_REVERSAL_STATE_CROUCH")
    if "A" in value:
        bits.append("IK_CNS_REVERSAL_STATE_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def hit_mask(text: str | None) -> str:
    value = (text or "MAF").strip().upper()
    bits: list[str] = []
    if "H" in value:
        bits.append("IK_CNS_HIT_STAND")
    if "L" in value:
        bits.append("IK_CNS_HIT_CROUCH")
    if "M" in value:
        bits += ["IK_CNS_HIT_STAND", "IK_CNS_HIT_CROUCH"]
    if "A" in value:
        bits.append("IK_CNS_HIT_AIR")
    if "F" in value:
        bits.append("IK_CNS_HIT_FALL")
    if "D" in value:
        bits.append("IK_CNS_HIT_DOWN")
    if "+" in value:
        bits.append("IK_CNS_HIT_ONLY_GETHIT")
    if "-" in value:
        bits.append("IK_CNS_HIT_NOT_GETHIT")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


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
    triggers = ctrl.all("trigger1")
    trigger2 = ctrl.all("trigger2")
    trigger3 = ctrl.all("trigger3")

    anim_or: list[str] = []
    for trigger_index in range(1, 9):
        group = ctrl.all(f"trigger{trigger_index}")
        # Lines of one triggerN are ANDed: two different `AnimElem = n` in a
        # group can never both hold, so that group drops out of the OR.
        if len(set(group)) > 1 and all(
                re.fullmatch(r"AnimElem\s*=\s*\d+", g.strip(), flags=re.I)
                for g in group):
            continue
        anim_or.extend(group)
    if 2 <= len(anim_or):
        elems: list[int] = []
        for expr in anim_or:
            m = re.fullmatch(
                r"AnimElem\s*=\s*(\d+)",
                _strip_outer_parens(expr),
                flags=re.I,
            )
            if not m:
                elems = []
                break
            elems.append(int(m.group(1)))
        if elems and all(1 <= e <= 32 for e in elems):
            mask = 0
            for elem in elems:
                mask |= 1 << (elem - 1)
            lo = mask & 0xffff
            hi = (mask >> 16) & 0xffff
            if lo >= 32768:
                lo -= 65536
            if hi >= 32768:
                hi -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_MASK", lo, hi

    if len(triggers) == 1 and len(trigger2) == 1:
        m0 = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        m1 = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)",
            _strip_outer_parens(trigger2[0]),
            flags=re.I,
        )
        if m0 and m1:
            return (
                "IK_CNS_TRIGGER_ANIM_ELEM_EQ_OR",
                int(m0.group(1)),
                int(m1.group(1)),
            )

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])

        m_target = re.fullmatch(
            r"NumTarget(?:\s*\(\s*(-?\d+)\s*\))?"
            r"\s*(=|!=|<=|>=|<|>)\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m_target:
            op = {
                "=": "IK_CNS_QUERY_EQ",
                "!=": "IK_CNS_QUERY_NE",
                "<": "IK_CNS_QUERY_LT",
                "<=": "IK_CNS_QUERY_LE",
                ">": "IK_CNS_QUERY_GT",
                ">=": "IK_CNS_QUERY_GE",
            }[m_target.group(2)]
            return (
                "IK_CNS_TRIGGER_NUM_TARGET_QUERY",
                int(m_target.group(3)),
                op,
            )

        m = re.fullmatch(
            r"(NumProj|ProjContact|ProjHit|ProjGuarded|"
            r"ProjContactTime|ProjHitTime|ProjGuardedTime)"
            r"\s*(=|!=|<=|>=|<|>)\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m:
            field = {
                "numproj": "IK_CNS_PROJ_QUERY_NUM",
                "projcontact": "IK_CNS_PROJ_QUERY_CONTACT",
                "projhit": "IK_CNS_PROJ_QUERY_HIT",
                "projguarded": "IK_CNS_PROJ_QUERY_GUARDED",
                "projcontacttime": "IK_CNS_PROJ_QUERY_CONTACT_TIME",
                "projhittime": "IK_CNS_PROJ_QUERY_HIT_TIME",
                "projguardedtime": "IK_CNS_PROJ_QUERY_GUARDED_TIME",
            }[m.group(1).lower()]
            op = {
                "=": "IK_CNS_QUERY_EQ",
                "!=": "IK_CNS_QUERY_NE",
                "<": "IK_CNS_QUERY_LT",
                "<=": "IK_CNS_QUERY_LE",
                ">": "IK_CNS_QUERY_GT",
                ">=": "IK_CNS_QUERY_GE",
            }[m.group(2)]
            packed_expr = f"(({field}) << 8) | ({op})"
            return (
                "IK_CNS_TRIGGER_PROJECTILE_QUERY",
                int(m.group(3)),
                packed_expr,
            )

        m = re.fullmatch(r"RoundState\s*=\s*(\d+)", value, flags=re.I)
        if m:
            return "IK_CNS_TRIGGER_ROUND_STATE_EQ", int(m.group(1)), 0
        m = re.fullmatch(r"RoundState\s*!=\s*(\d+)", value, flags=re.I)
        if m:
            return "IK_CNS_TRIGGER_ROUND_STATE_NE", int(m.group(1)), 0

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)\s*,\s*>=\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_FROM", int(m.group(1)), 0

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)\s*,\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            offset = int(m.group(2))
            if elem < 1 or elem > 255 or offset < -128 or offset > 127:
                raise ValueError(
                    f"[{ctrl.name}] AnimElem offset trigger out of range"
                )
            packed = (elem << 8) | (offset & 0xff)
            if packed >= 32768:
                packed -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED", packed, 0

    if ctype == "afterimagetime" and len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_FROM", int(m.group(1)), 0
        m = re.fullmatch(
            r"Vel\s+Y\s*<\s*(-?\d+(?:\.\d+)?)",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_VY_LT_Q8", q8(float(m.group(1))), 0

        m = re.fullmatch(
            r"AnimTime\s*<\s*(-\d+)",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_ANIM_TIME_REMAIN_GT",
                abs(int(m.group(1))),
                0,
            )

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*(\d+)\s*"
            r"&&\s*Time\s*<\s*(\d+)",
            value,
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            min_time = int(m.group(2))
            state_limit = int(m.group(3))
            if not (1 <= elem <= 255 and 0 <= min_time <= 255):
                raise ValueError(
                    f"[{ctrl.name}] AfterImageTime window out of range"
                )
            packed = (elem << 8) | min_time
            if packed >= 32768:
                packed -= 65536
            return (
                "IK_CNS_TRIGGER_ANIM_ELEM_TIME_GE_STATE_TIME_LT",
                packed,
                state_limit,
            )

    if ctype in ("width", "targetbind", "nothitby") and len(triggers) == 1:
        parsed = _anim_elem_range_trigger(triggers[0])
        if parsed is not None:
            return "IK_CNS_TRIGGER_ANIM_ELEM_RANGE", parsed[0], parsed[1]

    if ctype == "targetbind" and len(triggers) == 1:
        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

    if ctype in ("turn", "posadd", "targetfacing") and len(triggers) == 2:
        normalized = [_strip_outer_parens(t) for t in triggers]
        if any(re.fullmatch(r"var\(\s*2\s*\)", t, flags=re.I)
               for t in normalized):
            elem = next((
                re.fullmatch(r"AnimElem\s*=\s*(\d+)", t, flags=re.I)
                for t in normalized
                if re.fullmatch(r"AnimElem\s*=\s*(\d+)", t, flags=re.I)
            ), None)
            if elem:
                return (
                    "IK_CNS_TRIGGER_STATE_AXIS_FWD_ANIM_ELEM_EQ",
                    int(elem.group(1)), 0,
                )

    if ctype in ("selfstate", "changestate"):
        if ctype == "selfstate" and len(triggers) == 1 and re.fullmatch(
            r"!\s*gethitvar\s*\(\s*isbound\s*\)",
            triggers[0], flags=re.I
        ):
            return "IK_CNS_TRIGGER_NOT_BOUND", 0, 0
        target = integer(ctrl.get("value"), -1)
        trigger_all = ctrl.all("triggerall")
        if target == 5200 and trigger_all:
            return "IK_CNS_TRIGGER_THROW_GROUND_RECOVERY", q8(-20), 0
        if target == 5210 and trigger_all:
            return "IK_CNS_TRIGGER_THROW_AIR_RECOVERY", 0, 0
        normalized = [_strip_outer_parens(t) for t in triggers]
        if ctype == "changestate" and not trigger_all:
            masks = {"holdback": 2, "holddown": 8, "blocking": 128}
            flat = [
                _strip_outer_parens(p)
                for t in normalized
                for p in re.split(r"\s*&&\s*", t)
            ]
            time_eq = [re.fullmatch(r"Time\s*=\s*(\d+)", t, flags=re.I)
                       for t in flat]
            held = [re.fullmatch(r'Command\s*(!?=)\s*"(\w+)"', t, flags=re.I)
                    for t in flat]
            if (len(flat) == 2 and time_eq[0] and held[1] and
                    held[1].group(1) == "=" and
                    held[1].group(2).lower() in ("holdback",)):
                return ("IK_CNS_TRIGGER_TIME_EQ_COMMAND_ACTIVE",
                        int(time_eq[0].group(1)),
                        masks[held[1].group(2).lower()])
            if (flat and all(h and h.group(2).lower() in masks for h in held)
                    and any(h.group(1) == "=" and
                            h.group(2).lower() == "blocking" for h in held)):
                need = 0
                forbid = 0
                for h in held:
                    bit = masks[h.group(2).lower()]
                    if h.group(1) == "=":
                        need |= bit
                    else:
                        forbid |= bit
                return "IK_CNS_TRIGGER_COMMAND_ALL_NONE", need, forbid
        if ctype == "selfstate":
            split = normalized
            if len(normalized) == 1:
                split = [
                    _strip_outer_parens(p)
                    for p in re.split(r"\s*&&\s*", normalized[0])
                ]
            if (len(split) == 2 and
                any(re.fullmatch(r"Vel\s+Y\s*>\s*0", t, flags=re.I)
                    for t in split) and
                any(re.fullmatch(r"Pos\s+Y\s*>=\s*0", t, flags=re.I)
                    for t in split)):
                return "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0

    if ctype == "afterimagetime" and len(triggers) == 1:
        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*(\d+)\s*&&\s*"
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*(\d+)",
            _strip_outer_parens(triggers[0]), flags=re.I)
        if m:
            a, lo, b, hi = (int(g) for g in m.groups())
            if 1 <= a <= 255 and 1 <= b <= 255 and lo <= 255 and hi <= 255:
                return ("IK_CNS_TRIGGER_ANIM_ELEM_TIME_WINDOW",
                        (a << 8) | lo, (b << 8) | hi)

    if ctype == "width" and len(triggers) == 1:
        parsed = _anim_elem_range_trigger(triggers[0])
        if parsed is not None:
            return "IK_CNS_TRIGGER_ANIM_ELEM_RANGE", parsed[0], parsed[1]

    trigger_all = ctrl.all("triggerall")

    if ctype == "changestate" and len(triggers) in (2, 3):
        normalized = [_strip_outer_parens(t) for t in triggers]
        cmd = next((
            t for t in normalized
            if re.fullmatch(
                r'Command\s*=\s*"a"\s*\|\|\s*Command\s*=\s*"b"',
                t, flags=re.I
            )
        ), None)
        vy = next((
            re.fullmatch(r"Vel\s+y\s*<\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            for t in normalized
            if re.fullmatch(r"Vel\s+y\s*<\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
        ), None)
        time_ok = all(
            re.fullmatch(r"Time\s*>\s*0", t, flags=re.I)
            for t in normalized
            if t != cmd and (not vy or t != vy.group(0))
        )
        if cmd is not None and vy and time_ok:
            return (
                ("IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8_AFTER_ENTRY"
                 if len(normalized) == 3 else "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8"),
                (1 << 5) | (1 << 6),
                q8(float(vy.group(1))),
            )

    if ctype == "changestate" and len(triggers) == 1 and not trigger_all:
        value = _strip_outer_parens(triggers[0])
        parts = [
            _strip_outer_parens(p)
            for p in re.split(r"\s*&&\s*", value)
        ]
        if len(parts) == 2:
            vy = next((
                re.fullmatch(r"Vel\s+Y\s*>\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
                for t in parts
                if re.fullmatch(r"Vel\s+Y\s*>\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            ), None)
            pos = next((
                re.fullmatch(r"Pos\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
                for t in parts
                if re.fullmatch(r"Pos\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            ), None)
            if vy and pos:
                return (
                    "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL",
                    q8(float(pos.group(1))),
                    q8(float(vy.group(1))),
                )

    if ctype in ("changestate", "screenbound") and len(trigger_all) == 1 \
       and len(triggers) == 1 and len(trigger2) == 1:
        y = re.fullmatch(
            r"Pos\s+y\s*<\s*(-?\d+)",
            _strip_outer_parens(trigger_all[0]),
            flags=re.I,
        )
        back = re.fullmatch(
            r"BackEdgeBodyDist\s*(<=|<)\s*(\d+)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        front = re.fullmatch(
            r"FrontEdgeBodyDist\s*(<=|<)\s*(\d+)",
            _strip_outer_parens(trigger2[0]),
            flags=re.I,
        )
        if y and back and front and back.groups() == front.groups():
            return (
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE" +
                ("_LT" if back.group(1) == "<" else ""),
                q8(float(y.group(1))),
                int(back.group(2)),
            )

    if ctype == "turn" and len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"\(?\s*Time\s*=\s*0\s*\)?\s*&&\s*"
            r"\(?\s*FrontEdgeBodyDist\s*<=\s*(\d+)\s*\)?",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE",
                int(m.group(1)), 0,
            )
        m = re.fullmatch(
            r"\(?\s*Time\s*=\s*0\s*\)?\s*&&\s*"
            r"\(?\s*BackEdgeDist\s*<\s*(\d+)\s*\)?",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_STATE_ENTRY_BACK_EDGE_LT",
                int(m.group(1)), 0,
            )

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        if re.fullmatch(r"MoveHit", value, flags=re.I):
            return "IK_CNS_TRIGGER_MOVE_HIT", 0, 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*=\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            first = int(m.group(2))
            last = int(m.group(3))
            if not (1 <= elem <= 32767 and -128 <= first <= 127 and -128 <= last <= 127):
                raise ValueError(
                    f"[{ctrl.name}] AnimElemTime range trigger out of range"
                )
            packed = ((first & 0xff) << 8) | (last & 0xff)
            if packed >= 32768:
                packed -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_RANGE", elem, packed

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_AFTER", int(m.group(1)), 0

        m = re.fullmatch(
            r"Vel\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_VY_GE_Q8", q8(float(m.group(1))), 0

    if len(triggers) == 1 and re.fullmatch(
        r"HitShakeOver\s*=\s*1",
        _strip_outer_parens(triggers[0]),
        flags=re.I,
    ):
        return "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0

    if ctype == "changeanim":
        parsed = _move_contact_window(triggers)
        if parsed is not None:
            return (
                "IK_CNS_TRIGGER_MOVE_CONTACT_ELEM_WINDOW",
                parsed[0],
                parsed[1],
            )

    return simple_trigger(ctrl)


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


def compile_runtime_controller(
    state_no: int,
    ctrl: Section,
) -> dict | None:
    ctype = (ctrl.get("type", "") or "").strip().lower()

    supported = {
        "changestate",
        "ctrlset",
        "posadd",
        "posset",
        "sprpriority",
        "changeanim",
        "changeanim2",
        "statetypeset",
        "width",
        "varset",
        "varadd",
        "targetbind",
        "targetfacing",
        "targetlifeadd",
        "targetstate",
        "targetdrop",
        "screenbound",
        "turn",
        "selfstate",
        "veladd",
        "velset",
        "velmul",
        "hitvelset",
        "posfreeze",
        "destroyself",
        "pause",
        "superpause",
        "nothitby",
        "envshake",
        "afterimage",
        "afterimagetime",
        "palfx",
        "assertspecial",
        "makedust",
        "gravity",
        "poweradd",
    }
    if ctype not in supported:
        return None

    ctrl.runtime_trigger_expr = None
    ctrl.runtime_value0_expr = None
    ctrl.runtime_value1_expr = None
    try:
        trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, ctype)
    except ValueError:
        ctrl.runtime_trigger_expr = compile_controller_trigger_expr(ctrl)
        trig_kind, trig_value, trig_value2 = "IK_CNS_TRIGGER_ALWAYS", 0, 0
    if trig_kind == "IK_CNS_TRIGGER_ALWAYS":
        trigger_texts = [
            expr.strip().casefold()
            for trigger_index in range(1, 9)
            for expr in ctrl.all(f"trigger{trigger_index}")
        ]
        if trigger_texts and any(
            expr not in {"1", "1.0", "true"} for expr in trigger_texts
        ):
            try:
                ctrl.runtime_trigger_expr = compile_controller_trigger_expr(ctrl)
            except ValueError:
                if STRICT_CONVERSION:
                    raise

    flags: list[str] = []
    if integer(ctrl.get("ignorehitpause"), 0):
        flags.append("IK_CNS_CTRL_IGNORE_HIT_PAUSE")

    def flag_expr() -> str:
        return " | ".join(flags) if flags else "0u"

    if ctype == "assertspecial":
        flag = (ctrl.get("flag") or "").strip().lower()
        if flag != "intro":
            return None
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_ASSERT_INTRO",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "makedust":
        pos = pair(ctrl.get("pos"), 0, 0)
        spacing = integer(ctrl.get("spacing"), 0)
        if spacing not in (0, 1):
            return None
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_MAKE_DUST",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("anim"), 0),
            "value1": int(pos[0]),
            "value2": int(pos[1]),
            "flags": flag_expr(),
        }

    if ctype == "gravity":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_GRAVITY",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "poweradd":
        value_text = ctrl.get("value") or "0"
        try:
            value = eval_int(value_text)
            value_expr = None
        except ValueError:
            value = 0
            value_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = value_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POWER_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": value,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "palfx":
        def pack_rgb(text: str | None) -> int:
            parts = _split_top_level(text or "0,0,0")
            while len(parts) < 3:
                parts.append("0")
            values = [
                max(-255, min(255, integer(p, 0)))
                for p in parts[:3]
            ]
            return (
                (values[0] & 0x1ff) |
                ((values[1] & 0x1ff) << 9) |
                ((values[2] & 0x1ff) << 18)
            )

        sin_parts = _split_top_level(ctrl.get("sinadd") or "0,0,0,1")
        while len(sin_parts) < 4:
            sin_parts.append("0")
        sin_cycle = max(1, integer(sin_parts[3], 1))

        mul_parts = _split_top_level(ctrl.get("mul") or "256,256,256")
        while len(mul_parts) < 3:
            mul_parts.append("256")
        mul_values = [
            max(0, min(511, integer(part, 256)))
            for part in mul_parts[:3]
        ]
        mul_packed = (
            (mul_values[0] & 0x1ff) |
            ((mul_values[1] & 0x1ff) << 9) |
            ((mul_values[2] & 0x1ff) << 18)
        )

        sinmul_parts = _split_top_level(ctrl.get("sinmul") or "0,0,0,1")
        while len(sinmul_parts) < 4:
            sinmul_parts.append("0")
        sinmul_values = [
            max(-255, min(255, integer(part, 0)))
            for part in sinmul_parts[:3]
        ]
        sinmul_packed = (
            (sinmul_values[0] & 0x1ff) |
            ((sinmul_values[1] & 0x1ff) << 9) |
            ((sinmul_values[2] & 0x1ff) << 18)
        )
        sinmul_cycle = max(1, integer(sinmul_parts[3], 1))

        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_PAL_FX",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": pack_rgb(ctrl.get("add")),
            "value2": pack_rgb(",".join(sin_parts[:3])),
            "value3": sin_cycle,
            "value4": mul_packed,
            "value5": sinmul_packed,
            "value6": sinmul_cycle,
            "flags": flag_expr(),
        }

    if ctype == "afterimage":
        def pack_rgb_signed(text: str | None, defaults: tuple[int, int, int]) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            values = list(defaults)
            for i, part in enumerate(parts[:3]):
                values[i] = max(-128, min(127, integer(part, values[i])))
            packed = (
                (values[0] & 0xff) |
                ((values[1] & 0xff) << 8) |
                ((values[2] & 0xff) << 16)
            )
            return packed if packed < 0x80000000 else packed - 0x100000000

        def pack_rgb_unsigned(text: str | None, defaults: tuple[int, int, int]) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            values = list(defaults)
            for i, part in enumerate(parts[:3]):
                values[i] = max(0, min(255, integer(part, values[i])))
            return values[0] | (values[1] << 8) | (values[2] << 16)

        def pack_mul(text: str | None) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            defaults = [1.0, 1.0, 1.0]
            values = defaults[:]
            for i, part in enumerate(parts[:3]):
                values[i] = max(0.0, min(1.0, number(part)))
            q = [max(0, min(255, int(round(v * 255.0)))) for v in values]
            return q[0] | (q[1] << 8) | (q[2] << 16)

        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_AFTER_IMAGE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": integer(ctrl.get("length"), 20),
            "value2": integer(ctrl.get("timegap"), 1),
            "value3": integer(ctrl.get("framegap"), 4),
            "value4": pack_rgb_signed(ctrl.get("palbright"), (30, 30, 30)),
            "value5": pack_rgb_unsigned(ctrl.get("palcontrast"), (120, 120, 220)),
            "value6": pack_rgb_signed(ctrl.get("paladd"), (10, 10, 25)),
            "value7": pack_mul(
                ctrl.get("palmul") or ".65,.65,.75"
            ),
            "flags": flag_expr(),
        }

    if ctype == "afterimagetime":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_AFTER_IMAGE_TIME",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "envshake":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_ENV_SHAKE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 0),
            "value1": integer(ctrl.get("ampl"), 0),
            "flags": flag_expr(),
        }

    if ctype == "superpause":
        if integer(ctrl.get("darken"), 1):
            flags.append("IK_CNS_CTRL_SUPER_DARKEN")
        if ctrl.get("anim") is not None:
            flags.append("IK_CNS_CTRL_HAS_SUPER_ANIM")
        pos_x, pos_y = pair(ctrl.get("pos"), 0, 0)
        packed_pos = ((int(pos_x) & 0xffff) << 16) | (int(pos_y) & 0xffff)
        if packed_pos >= 0x80000000:
            packed_pos -= 0x100000000
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SUPER_PAUSE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 30),
            "value1": integer(ctrl.get("poweradd"), 0),
            "value2": integer(ctrl.get("anim"), -1),
            "value3": packed_pos,
            "value4": integer(ctrl.get("movetime"), 0),
            "value5": integer(ctrl.get("endcmdbuftime"), 0),
            "value6": integer(ctrl.get("pausebg"), 1),
            "value7": integer(ctrl.get("brightness"), 0),
            "flags": flag_expr(),
        }

    if ctype == "pause":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_PAUSE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 0),
            "value1": integer(ctrl.get("movetime"), 0),
            "value2": integer(ctrl.get("endcmdbuftime"), 0),
            "value3": integer(ctrl.get("pausebg"), 1),
            "flags": flag_expr(),
        }

    if ctype == "nothitby":
        raw = ctrl.get("value")
        if raw is None:
            raw = ctrl.get("value2")
        state_mask = no_hit_by_state_mask(raw)
        attr_mask = no_hit_by_attr_mask(raw)
        if state_mask == "0u" and attr_mask == "0u":
            return None
        packed = (
            f"({state_mask}) | (({attr_mask}) << 8)"
            if attr_mask != "0u"
            else state_mask
        )
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_NOT_HIT_BY",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": packed,
            "value1": integer(ctrl.get("time"), 1),
            "flags": flag_expr(),
        }

    if ctype == "changestate":
        has_ctrl = ctrl.get("ctrl") is not None
        if has_ctrl:
            flags.append("IK_CNS_CTRL_HAS_CTRL")
        value_text = ctrl.get("value") or "-1"
        try:
            state_no = eval_int(value_text)
            state_expr = None
        except ValueError:
            state_no = 0
            state_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = state_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": state_no,
            "value1": integer(ctrl.get("ctrl"), 0),
            "flags": flag_expr(),
        }

    if ctype == "ctrlset":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CTRL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "flags": flag_expr(),
        }

    if ctype == "posadd":
        x_text = (ctrl.get("x") or "0").strip()
        m = re.fullmatch(
            r"(-?\d+)\s*-\s*BackEdgeBodyDist",
            x_text,
            flags=re.I,
        )
        if m and ctrl.get("y") is None:
            return {
                "state_number": state_no,
                "type": "IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE",
                "trigger_kind": trig_kind,
                "trigger_value": trig_value,
                "trigger_value2": trig_value2,
                "value0": q8(float(m.group(1))),
                "value1": 0,
                "flags": flag_expr(),
            }
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{x_text},{ctrl.get('y') or '0'}", 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value2": integer(ctrl.get("id"), -1),
            "flags": flag_expr(),
        }

    if ctype == "posset":
        x = number(ctrl.get("x"), 0)
        y = number(ctrl.get("y"), 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis.append("IK_CNS_CTRL_AXIS_X")
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "sprpriority":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SPR_PRIORITY",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "changeanim":
        value_text = ctrl.get("value") or "-1"
        try:
            anim_no = eval_int(value_text)
            anim_expr = None
        except ValueError:
            anim_no = 0
            anim_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = anim_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_ANIM",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": anim_no,
            "value1": integer(ctrl.get("elem"), 1),
            "flags": flag_expr(),
        }

    if ctype == "changeanim2":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_ANIM2",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 1,
            "flags": flag_expr(),
        }

    if ctype == "statetypeset":
        state_type = (ctrl.get("statetype") or "U").strip().upper()
        move_type = (ctrl.get("movetype") or "U").strip().upper()
        physics = (ctrl.get("physics") or "U").strip().upper()
        set_flags = []
        if state_type not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_STATE_TYPE")
        if move_type not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_MOVE_TYPE")
        if physics not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_PHYSICS")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_STATE_TYPE_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": STATE_TYPE.get(state_type, "IK_CNS_STATE_UNCHANGED"),
            "value1": MOVE_TYPE.get(move_type, "IK_CNS_MOVE_UNCHANGED"),
            "value2": PHYSICS.get(physics, "IK_CNS_PHYS_BY_TYPE"),
            "value3": " | ".join(set_flags) if set_flags else "0u",
            "flags": flag_expr(),
        }

    if ctype in ("varset", "varadd"):
        if ctype == "varset":
            var2 = ctrl.get("var(2)")
            if var2 is not None and re.fullmatch(
                r'command\s*=\s*"holdfwd"', var2.strip(), flags=re.I
            ):
                return {
                    "state_number": state_no,
                    "type": "IK_CNS_CTRL_CAPTURE_COMMAND_AXIS",
                    "trigger_kind": trig_kind,
                    "trigger_value": trig_value,
                    "trigger_value2": trig_value2,
                    "value0": 0,
                    "value1": 0,
                    "flags": flag_expr(),
                }

        var_index = None
        var_value_text = None
        var_is_system = False
        if ctrl.get("v") is not None and ctrl.get("value") is not None:
            var_index = integer(ctrl.get("v"))
            var_value_text = ctrl.get("value")
        else:
            assignments = []
            for key, value in ctrl.values:
                match = re.fullmatch(r"var\((\d+)\)", key.strip(), flags=re.I)
                if match:
                    assignments.append((int(match.group(1)), value, False))
                match = re.fullmatch(r"sysvar\((\d+)\)", key.strip(), flags=re.I)
                if match:
                    assignments.append((int(match.group(1)), value, True))
            if len(assignments) == 1:
                var_index, var_value_text, var_is_system = assignments[0]

        if var_index is None or var_value_text is None:
            return None
        var_count = 4 if var_is_system else 60
        if var_index < 0 or var_index >= var_count:
            raise ValueError(
                f"[{ctrl.name}] {'sysvar' if var_is_system else 'var'} "
                f"index outside 0..{var_count - 1}")
        var_value = integer(var_value_text)
        if var_value < -2147483648 or var_value > 2147483647:
            raise ValueError(f"[{ctrl.name}] var value outside int32")
        return {
            "state_number": state_no,
            "type": (
                "IK_CNS_CTRL_SYSVAR_SET" if var_is_system else
                "IK_CNS_CTRL_VAR_SET" if ctype == "varset" else
                "IK_CNS_CTRL_VAR_ADD"
            ),
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": var_index,
            "value1": var_value,
            "flags": flag_expr(),
        }

    if ctype == "screenbound":
        # value3 bit 0: `value` given, bit 1: `movecamera` given.
        move = ctrl.get("movecamera")
        move_x, move_y = pair(move, 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SCREEN_BOUND",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value"), 0),
            "value1": int(move_x),
            "value2": int(move_y),
            "value3": int(ctrl.get("value") is not None) |
                      (int(move is not None) << 1),
            "flags": flag_expr(),
        }

    if ctype == "targetdrop":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_DROP",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("excludeid"), -1),
            "value1": integer(ctrl.get("keepone"), 1),
            "value7": (
                integer(
                    re.search(
                        r"NumTarget\s*\(\s*(-?\d+)\s*\)",
                        " ".join(ctrl.all("trigger1")),
                        flags=re.I,
                    ).group(1)
                )
                if re.search(
                    r"NumTarget\s*\(\s*(-?\d+)\s*\)",
                    " ".join(ctrl.all("trigger1")),
                    flags=re.I,
                )
                else -1
            ),
            "flags": flag_expr(),
        }

    if ctype == "targetbind":
        x, y = pair(ctrl.get("pos"), 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_BIND",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetfacing":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_FACING",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value"), 1),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetlifeadd":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_LIFE_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetstate":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "turn":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TURN",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "posfreeze":
        flags2: list[str] = []
        if ctrl.get("x") is None and ctrl.get("y") is None:
            # MUGEN PosFreeze defaults to freezing both axes.
            flags2 += ["IK_CNS_CTRL_AXIS_X", "IK_CNS_CTRL_AXIS_Y"]
        else:
            if integer(ctrl.get("x"), 0):
                flags2.append("IK_CNS_CTRL_AXIS_X")
            if integer(ctrl.get("y"), 0):
                flags2.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_FREEZE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": " | ".join(flags2 + flags) if flags2 or flags else "0u",
        }

    if ctype == "destroyself":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_DESTROY_SELF",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "selfstate":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SELF_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "veladd":
        x_text = ctrl.get("x")
        y_text = ctrl.get("y")
        use_yaccel = bool(
            y_text is not None and re.fullmatch(
                r"Const\s*\(\s*movement\.yaccel\s*\)",
                y_text.strip(),
                flags=re.I,
            )
        )
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{x_text or '0'},"
                f"{'0' if use_yaccel else (y_text or '0')}", 0, 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis.append("IK_CNS_CTRL_AXIS_X")
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        if use_yaccel:
            flags.append("IK_CNS_CTRL_USE_YACCEL")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value4": q16(x),
            "value5": q16(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "velset":
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{ctrl.get('x') or '0'},{ctrl.get('y') or '0'}", 0, 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis += ["IK_CNS_CTRL_AXIS_X", "IK_CNS_CTRL_LOCAL_X"]
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value4": q16(x),
            "value5": q16(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "hitvelset":
        axis: list[str] = []
        if integer(ctrl.get("x"), 0):
            axis.append("IK_CNS_CTRL_AXIS_X")
        if integer(ctrl.get("y"), 0):
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_HIT_VEL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "velmul":
        plain = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
        xtext = (ctrl.get("x") or "").strip()
        ytext = (ctrl.get("y") or "").strip()
        if (xtext or ytext) and all(
            not t or plain.fullmatch(t) for t in (xtext, ytext)
        ):
            axis = []
            if xtext:
                axis.append("IK_CNS_CTRL_AXIS_X")
            if ytext:
                axis.append("IK_CNS_CTRL_AXIS_Y")
            return {
                "state_number": state_no,
                "type": "IK_CNS_CTRL_VEL_MUL",
                "trigger_kind": trig_kind,
                "trigger_value": trig_value,
                "trigger_value2": trig_value2,
                "value0": q8(number(xtext or None, 1)),
                "value1": q8(number(ytext or None, 1)),
                "flags": " | ".join(axis + flags) if flags else
                         " | ".join(axis),
            }
        xexpr = (ctrl.get("x") or "").strip()
        m = re.fullmatch(
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\*\s*"
            r"ifelse\s*\(\s*AnimElemTime\s*\(\s*(\d+)\s*\)"
            r"\s*<\s*0\s*,\s*1\s*,\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)",
            xexpr,
            flags=re.I,
        )
        if not m or ctrl.get("y") is not None:
            return None
        base = float(m.group(1))
        elem = int(m.group(2))
        tail = float(m.group(3))
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_MUL_X_BY_ANIM_ELEM",
            "trigger_kind": trig_kind,
            "trigger_value": elem,
            "trigger_value2": 0,
            "value0": q8(base),
            "value1": q8(base * tail),
            "flags": flag_expr(),
        }

    # `value` widens the player box and the screen-edge box, `player` and
    # `edge` only their own.
    value_text = ctrl.get("value")
    player = pair(ctrl.get("player", value_text), 0, 0)
    edge = pair(ctrl.get("edge", value_text), 0, 0)
    if any(int(v) != v for v in (*player, *edge)):
        raise ValueError(
            f"[{ctrl.name}] Width values must be integral in the Saturn subset"
        )
    return {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_WIDTH",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": int(player[0]),
        "value1": int(player[1]),
        "value2": int(edge[0]),
        "value3": int(edge[1]),
        "flags": flag_expr(),
    }



def compile_helper_controller(
    state_no: int,
    ctrl: Section,
    helper_index: int,
) -> tuple[dict, dict] | None:
    supported_keys = {
        "type", "helpertype", "postype", "ownpal", "stateno",
        "keyctrl", "id", "pos", "facing", "ignorehitpause",
        "pausemovetime", "supermovetime",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported_keys:
            return None

    helper_type = (ctrl.get("helpertype", "normal") or "normal").strip().lower()
    if helper_type not in ("normal", ""):
        return None

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_HELPER_POS_P1",
        "p2": "IK_CNS_HELPER_POS_P2",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return None

    trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, "helper")
    px, py = pair(ctrl.get("pos"), 0, 0)
    facing = integer(ctrl.get("facing"), 1)
    if facing == 0:
        facing = 1
    facing = 1 if facing > 0 else -1

    helper = {
        "id": integer(ctrl.get("id"), 0),
        "state_no": integer(ctrl.get("stateno"), 0),
        "pos_x_q8": q8(px),
        "pos_y_q8": q8(py),
        "facing": facing,
        "postype": postype,
        # MUGEN booleans commonly use 99999 for true. These fields are
        # represented as uint8_t flags in the runtime, so preserve truth
        # semantics instead of truncating the source integer (99999 -> 159).
        "keyctrl": int(integer(ctrl.get("keyctrl"), 0) != 0),
        "ownpal": int(integer(ctrl.get("ownpal"), 0) != 0),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_HELPER",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": helper_index,
        "value1": 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    return controller, helper

def guard_times(ctrl: Section) -> tuple[int, int, int]:
    """(hittime, slidetime, ctrltime) of a guarded hit.

    Mugen characters (classic KFM) default guard.hittime to ground.slidetime,
    not ground.hittime as documented; Ikemen's engine does the same for them.
    """
    hit = eval_int(ctrl.get("guard.hittime"),
                  eval_int(ctrl.get("ground.slidetime"), 0))
    slide = eval_int(ctrl.get("guard.slidetime"), hit)
    return hit, slide, eval_int(ctrl.get("guard.ctrltime"), slide)


def guard_times_runtime(
    ctrl: Section,
    ground_slide: int,
    ground_slide_expr: list[dict] | None,
) -> tuple[tuple[int, int, int], tuple[list[dict] | None, ...]]:
    """Compile guarded hit clocks, preserving MUGEN's inherited defaults."""
    if ctrl.get("guard.hittime") is not None:
        hit, hit_expr = integer_or_runtime_expr(ctrl.get("guard.hittime"), 0)
    else:
        hit, hit_expr = ground_slide, ground_slide_expr
    if ctrl.get("guard.slidetime") is not None:
        slide, slide_expr = integer_or_runtime_expr(ctrl.get("guard.slidetime"), hit)
    else:
        slide, slide_expr = hit, hit_expr
    if ctrl.get("guard.ctrltime") is not None:
        control, control_expr = integer_or_runtime_expr(ctrl.get("guard.ctrltime"), slide)
    else:
        control, control_expr = slide, slide_expr
    return (hit, slide, control), (hit_expr, slide_expr, control_expr)


def _projectile_hitdef_row(
    state_no: int,
    ctrl: Section,
    default_spark_no: int,
    default_guard_spark_no: int,
) -> dict:
    damage, guard_damage = pair(ctrl.get("damage") or "0,0", 0, 0)
    pause1, pause2 = pair(ctrl.get("pausetime"), 0, 0)
    gx, gy = pair(ctrl.get("ground.velocity"), 0, 0)
    ax, ay = pair(ctrl.get("air.velocity"), gx, gy)
    guardx = number(ctrl.get("guard.velocity"), gx)
    agx, agy = pair(ctrl.get("airguard.velocity"), ax * 1.5, ay / 2.0)
    down_x, down_y = pair(ctrl.get("down.velocity"), ax, ay)
    sparkx, sparky, _ = spark_pair(ctrl.get("sparkxy"))
    hs = sound_pair(ctrl.get("hitsound"))
    gs = sound_pair(ctrl.get("guardsound"))
    air_juggle, air_juggle_expr = integer_or_runtime_expr(
        ctrl.get("air.juggle"), 0)

    attr_parts = [
        p.strip().upper()
        for p in (ctrl.get("attr") or "S, NP").split(",")
    ]
    attack_attr = attack_attr_mask(
        attr_parts[1] if len(attr_parts) > 1 else "NP"
    )
    flags: list[str] = []
    if integer(ctrl.get("fall"), 0):
        flags.append("IK_CNS_HITDEF_FALL")
    if integer(ctrl.get("air.fall"), 0):
        flags.append("IK_CNS_HITDEF_AIR_FALL")
    if integer(ctrl.get("forcestand"), 0):
        flags.append("IK_CNS_HITDEF_FORCE_STAND")
    if integer(ctrl.get("forcenofall"), 0):
        flags.append("IK_CNS_HITDEF_FORCE_NO_FALL")

    return {
        "state_number": state_no,
        "trigger_kind": "IK_CNS_TRIGGER_ALWAYS",
        "trigger_value": 0,
        "damage": int(damage),
        "guard_damage": int(guard_damage),
        "priority": integer(
            (ctrl.get("priority") or "4").split(",", 1)[0], 4),
        "pause_p1": int(pause1),
        "pause_p2": int(pause2),
        "ground_type": GROUND_TYPE.get(
            (ctrl.get("ground.type", "normal") or "normal").strip().lower(),
            "IK_CNS_GROUND_NORMAL"),
        "ground_slide_time": integer(ctrl.get("ground.slidetime"), 0),
        "ground_hit_time": integer(ctrl.get("ground.hittime"), 0),
        "air_hit_time": integer(
            ctrl.get("air.hittime"),
            integer(ctrl.get("ground.hittime"), 0)),
        "ground_velocity_x_q8": q8(gx),
        "ground_velocity_y_q8": q8(gy),
        "air_velocity_x_q8": q8(ax),
        "air_velocity_y_q8": q8(ay),
        "spark_no": integer(ctrl.get("sparkno"), default_spark_no),
        "spark_x": int(sparkx),
        "spark_y": int(sparky),
        "hit_sound_group": hs[0],
        "hit_sound_item": hs[1],
        "guard_sound_group": gs[0],
        "guard_sound_item": gs[1],
        "flags": " | ".join(flags) if flags else "0u",
        "guard_flags": guard_mask(ctrl.get("guardflag")),
        "guard_kill": integer(ctrl.get("guard.kill"), 1),
        "guard_slide_time": guard_times(ctrl)[1],
        "guard_hit_time": guard_times(ctrl)[0],
        "guard_ctrl_time": guard_times(ctrl)[2],
        "guard_velocity_x_q8": q8(guardx),
        "air_guard_velocity_x_q8": q8(agx),
        "air_guard_velocity_y_q8": q8(agy),
        "anim_type": anim_type_code(ctrl.get("animtype")),
        "air_anim_type": anim_type_code(
            ctrl.get("air.animtype") or ctrl.get("animtype")),
        "fall_anim_type": fall_anim_type_code(ctrl),
        "fall_x_velocity_q8": q8(number(ctrl.get("fall.xvelocity"), 0)),
        "fall_y_velocity_q8": q8(number(ctrl.get("fall.yvelocity"), -4.5)),
        "fall_x_velocity_set": int(ctrl.get("fall.xvelocity") is not None),
        "fall_recover": integer(
            ctrl.get("fall.recover"), integer(ctrl.get("air.recover"), 1)),
        "fall_recover_time": integer(ctrl.get("fall.recovertime"), 4),
        "down_hit_time": integer(ctrl.get("down.hittime"), 0),
        "down_velocity_x_q8": q8(down_x),
        "down_velocity_y_q8": q8(down_y),
        "down_bounce": integer(ctrl.get("down.bounce"), 0),
        "hit_flags": hit_mask(ctrl.get("hitflag")),
        "priority_type": priority_type_code(ctrl.get("priority")),
        "air_juggle": air_juggle,
        "_air_juggle_expr": air_juggle_expr,
        "p1_state_no": integer(ctrl.get("p1stateno"), -1),
        "p2_state_no": integer(ctrl.get("p2stateno"), -1),
        "guard_dist": integer(ctrl.get("guard.dist"), -1),
        "p1_facing": integer(ctrl.get("p1facing"), 0),
        "p2_facing": integer(ctrl.get("p2facing"), 0),
        "p1_spr_priority": integer(ctrl.get("p1sprpriority"), -128),
        "p2_body_dist_op": "IK_CNS_P2_DIST_NONE",
        "p2_body_dist_x": 0,
        "alt_damage": -1,
        "alt_damage_prev_state": -32768,
        "trigger2_kind": 255,
        "trigger2_value": 0,
        "yaccel_q8": q8(number(ctrl.get("yaccel"), .35)),
        "yaccel_q16": q16(number(ctrl.get("yaccel"), .35)),
        **power_fields(ctrl),
        **dist_fields(ctrl),
        "has_trigger2": 0,
        "has_alt_damage": 0,
        "ground_cornerpush_veloff_q8": q8(
            number(ctrl.get("ground.cornerpush.veloff"), 0)),
        "trigger2_spark_y": int(sparky),
        "guard_spark_no": integer(
            ctrl.get("guard.sparkno"), default_guard_spark_no),
        "attack_attr_mask": attack_attr,
        "fall_damage": integer(ctrl.get("fall.damage"), 0),
        "envshake_time": integer(ctrl.get("envshake.time"), 0),
        "envshake_ampl": integer(ctrl.get("envshake.ampl"), 0),
        "envshake_freq": integer(ctrl.get("envshake.freq"), 60),
        "fall_envshake_time": integer(ctrl.get("fall.envshake.time"), 0),
        "fall_envshake_ampl": integer(ctrl.get("fall.envshake.ampl"), 0),
        "fall_envshake_freq": integer(ctrl.get("fall.envshake.freq"), 60),
        "id": integer(ctrl.get("id"), 0),
        "chain_id": integer(ctrl.get("chainid"), -1),
        "no_chain_id": integer(
            (ctrl.get("nochainid") or "-1").split(",", 1)[0], -1),
        "no_chain_id2": integer(
            (ctrl.get("nochainid") or "-1,-1").split(",", 1)[1]
            if "," in (ctrl.get("nochainid") or "") else "-1",
            -1),
    }


def compile_projectile_controller(
    state_no: int,
    ctrl: Section,
    projectile_index: int,
    hitdef_global: int,
    default_spark_no: int,
    default_guard_spark_no: int,
) -> tuple[dict, dict, dict] | None:
    supported = {
        "type", "projid", "projanim", "projhitanim", "projremanim",
        "projshadow",
        "projcancelanim", "postype", "offset", "velocity", "velmul",
        "accel", "projremove", "projremovetime", "projhits",
        "projmisstime", "projpriority", "projsprpriority",
        "projedgebound", "projstagebound", "pausemovetime",
        "supermovetime", "ownpal", "persistent", "ignorehitpause",
        "bindtime", "removeongethit", "removeonchangestate",
        "attr", "damage", "priority", "pausetime", "sparkno",
        "guard.sparkno", "sparkxy", "hitsound", "guardsound",
        "animtype", "air.animtype", "fall", "air.fall",
        "forcestand", "forcenofall", "guardflag", "hitflag",
        "ground.type", "ground.slidetime", "ground.hittime",
        "ground.velocity", "air.hittime", "air.velocity",
        "getpower", "givepower",
        "guard.velocity", "airguard.velocity", "guard.slidetime",
        "guard.hittime", "guard.ctrltime", "guard.kill",
        "fall.xvelocity", "fall.yvelocity", "fall.recover",
        "fall.recovertime", "air.recover", "down.hittime", "down.velocity",
        "down.bounce", "air.juggle", "p1stateno", "p2stateno",
        "guard.dist", "p1facing", "p2facing", "p1sprpriority",
        "yaccel", "ground.cornerpush.veloff", "fall.damage",
        "envshake.time", "envshake.ampl", "envshake.freq",
        "fall.envshake.time", "fall.envshake.ampl",
        "fall.envshake.freq", "id", "chainid", "nochainid",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported:
            return None

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_HELPER_POS_P1",
        "p2": "IK_CNS_HELPER_POS_P2",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return None

    trig_kind, trig_value, trig_value2 = controller_trigger(
        ctrl, "projectile")
    ox, oy = pair(ctrl.get("offset"), 0, 0)
    vx, vy = pair(ctrl.get("velocity"), 0, 0)
    vmx, vmy = pair(ctrl.get("velmul"), 1, 1)
    ax, ay = pair(ctrl.get("accel"), 0, 0)
    shadow_parts = _split_top_level(ctrl.get("projshadow") or "0,0,0")
    while len(shadow_parts) < 3:
        shadow_parts.append("0")
    shadow_rgb = tuple(
        max(0, min(255, integer(part, 0))) for part in shadow_parts[:3])

    projectile = {
        "id": integer(ctrl.get("projid"), 0),
        "postype": postype,
        "anim_no": integer(ctrl.get("projanim"), 0),
        "hit_anim_no": integer(ctrl.get("projhitanim"), -1),
        "remove_anim_no": integer(ctrl.get("projremanim"), -1),
        "cancel_anim_no": integer(ctrl.get("projcancelanim"), -1),
        "hitdef_global": hitdef_global,
        "pos_x_q8": q8(ox),
        "pos_y_q8": q8(oy),
        "vel_x_q8": q8(vx),
        "vel_y_q8": q8(vy),
        "velmul_x_q8": q8(vmx),
        "velmul_y_q8": q8(vmy),
        "accel_x_q8": q8(ax),
        "accel_y_q8": q8(ay),
        "remove_time": integer(ctrl.get("projremovetime"), -1),
        "edge_bound": integer(ctrl.get("projedgebound"), 40),
        "stage_bound": integer(ctrl.get("projstagebound"), 40),
        "hits": max(1, integer(ctrl.get("projhits"), 1)),
        "miss_time": max(0, integer(ctrl.get("projmisstime"), 0)),
        "priority": max(0, integer(ctrl.get("projpriority"), 1)),
        "remove_on_hit": integer(ctrl.get("projremove"), 1),
        "spr_priority": integer(ctrl.get("projsprpriority"), 3),
        "ownpal": integer(ctrl.get("ownpal"), 0),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
        "bind_time": integer(ctrl.get("bindtime"), 0),
        "remove_on_gethit": integer(ctrl.get("removeongethit"), 0),
        "remove_on_state_change": integer(
            ctrl.get("removeonchangestate"), 0),
        "has_shadow": int(ctrl.get("projshadow") is not None),
        "shadow_r": shadow_rgb[0],
        "shadow_g": shadow_rgb[1],
        "shadow_b": shadow_rgb[2],
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_PROJECTILE",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": projectile_index,
        "value1": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    hitdef = _projectile_hitdef_row(
        state_no, ctrl, default_spark_no, default_guard_spark_no)
    return controller, projectile, hitdef


def compile_modify_projectile_controller(
    state_no: int,
    ctrl: Section,
    mod_index: int,
) -> tuple[dict, dict] | None:
    supported = {
        "type", "id", "index", "projanim", "projhitanim",
        "projremanim", "projcancelanim", "velocity", "velmul",
        "accel", "projremove", "projremovetime", "projhits",
        "projmisstime", "projpriority", "projsprpriority",
        "projedgebound", "projstagebound", "pausemovetime",
        "supermovetime", "bindtime", "removeongethit",
        "removeonchangestate", "persistent", "ignorehitpause",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported:
            return None

    mod_index_value = max(0, integer(ctrl.get("index"), 0))

    mask: list[str] = []
    def present(name: str, flag: str) -> bool:
        if ctrl.get(name) is None:
            return False
        mask.append(flag)
        return True

    has_velocity = present("velocity", "IK_CNS_PROJ_MOD_VELOCITY")
    has_velmul = present("velmul", "IK_CNS_PROJ_MOD_VELMUL")
    has_accel = present("accel", "IK_CNS_PROJ_MOD_ACCEL")
    vx, vy = pair(ctrl.get("velocity"), 0, 0)
    vmx, vmy = pair(ctrl.get("velmul"), 1, 1)
    ax, ay = pair(ctrl.get("accel"), 0, 0)

    fields = {
        "anim_no": integer(ctrl.get("projanim"), 0),
        "hit_anim_no": integer(ctrl.get("projhitanim"), -1),
        "remove_anim_no": integer(ctrl.get("projremanim"), -1),
        "cancel_anim_no": integer(ctrl.get("projcancelanim"), -1),
        "vel_x_q8": q8(vx),
        "vel_y_q8": q8(vy),
        "velmul_x_q8": q8(vmx),
        "velmul_y_q8": q8(vmy),
        "accel_x_q8": q8(ax),
        "accel_y_q8": q8(ay),
        "remove_time": integer(ctrl.get("projremovetime"), -1),
        "edge_bound": integer(ctrl.get("projedgebound"), 40),
        "stage_bound": integer(ctrl.get("projstagebound"), 40),
        "hits": max(1, integer(ctrl.get("projhits"), 1)),
        "miss_time": max(0, integer(ctrl.get("projmisstime"), 0)),
        "priority": max(0, integer(ctrl.get("projpriority"), 1)),
        "remove_on_hit": integer(ctrl.get("projremove"), 1),
        "spr_priority": integer(ctrl.get("projsprpriority"), 3),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
        "bind_time": integer(ctrl.get("bindtime"), 0),
        "remove_on_gethit": integer(ctrl.get("removeongethit"), 0),
        "remove_on_state_change": integer(
            ctrl.get("removeonchangestate"), 0),
    }

    for name, flag in (
        ("projanim", "IK_CNS_PROJ_MOD_ANIM"),
        ("projhitanim", "IK_CNS_PROJ_MOD_HIT_ANIM"),
        ("projremanim", "IK_CNS_PROJ_MOD_REMOVE_ANIM"),
        ("projcancelanim", "IK_CNS_PROJ_MOD_CANCEL_ANIM"),
        ("projremovetime", "IK_CNS_PROJ_MOD_REMOVE_TIME"),
        ("projhits", "IK_CNS_PROJ_MOD_HITS"),
        ("projmisstime", "IK_CNS_PROJ_MOD_MISS_TIME"),
        ("projpriority", "IK_CNS_PROJ_MOD_PRIORITY"),
        ("projsprpriority", "IK_CNS_PROJ_MOD_SPR_PRIORITY"),
        ("projedgebound", "IK_CNS_PROJ_MOD_EDGE_BOUND"),
        ("projstagebound", "IK_CNS_PROJ_MOD_STAGE_BOUND"),
        ("projremove", "IK_CNS_PROJ_MOD_REMOVE_ON_HIT"),
        ("pausemovetime", "IK_CNS_PROJ_MOD_PAUSE_MOVE"),
        ("supermovetime", "IK_CNS_PROJ_MOD_SUPER_MOVE"),
        ("bindtime", "IK_CNS_PROJ_MOD_BIND_TIME"),
        ("removeongethit", "IK_CNS_PROJ_MOD_REMOVE_ON_GETHIT"),
        ("removeonchangestate", "IK_CNS_PROJ_MOD_REMOVE_ON_STATE_CHANGE"),
    ):
        present(name, flag)

    # These were already recorded above before pair parsing.
    if not has_velocity:
        pass
    if not has_velmul:
        pass
    if not has_accel:
        pass

    mod = {
        "id": integer(ctrl.get("id"), -1),
        "index": mod_index_value,
        "mask": " | ".join(mask) if mask else "0u",
        **fields,
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_MODIFY_PROJECTILE",
        "trigger_kind": controller_trigger(
            ctrl, "modifyprojectile")[0],
        "trigger_value": controller_trigger(
            ctrl, "modifyprojectile")[1],
        "trigger_value2": controller_trigger(
            ctrl, "modifyprojectile")[2],
        "value0": mod_index,
        "value1": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    return controller, mod


def compile_explod_controller(
    state_no: int,
    ctrl: Section,
    explod_index: int,
) -> tuple[dict, dict] | None:
    supported_keys = {
        "type", "anim", "postype", "pos", "velocity", "accel",
        "removetime", "sprpriority", "persistent", "ignorehitpause",
        "ownpal", "pausemovetime", "supermovetime", "bindtime",
        "removeongethit", "removeonchangestate", "facing", "vfacing",
        "scale", "trans", "alpha",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported_keys:
            return None

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_HELPER_POS_P1",
        "p2": "IK_CNS_HELPER_POS_P2",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return None

    trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, "explod")
    px, py = pair(ctrl.get("pos"), 0, 0)
    vx, vy = pair(ctrl.get("velocity"), 0, 0)
    ax, ay = pair(ctrl.get("accel"), 0, 0)
    sx, sy = pair(ctrl.get("scale"), 1, 1)

    trans_text = (ctrl.get("trans") or "none").strip().lower()
    trans_map = {
        "none": "IK_CNS_TRANS_NONE",
        "default": "IK_CNS_TRANS_NONE",
        "alpha": "IK_CNS_TRANS_ALPHA",
        "addalpha": "IK_CNS_TRANS_ALPHA",
        "add": "IK_CNS_TRANS_ADD",
        "sub": "IK_CNS_TRANS_SUB",
    }
    if trans_text not in trans_map:
        return None

    alpha_src, _alpha_dst = pair(ctrl.get("alpha"), 256, 256)
    alpha_value = max(0, min(255, int(round(float(alpha_src) * 255.0 / 256.0))))

    explod = {
        "anim_no": integer(ctrl.get("anim"), 0),
        "pos_x_q8": q8(px, wide=True),
        "pos_y_q8": q8(py, wide=True),
        "vel_x_q8": q8(vx, wide=True),
        "vel_y_q8": q8(vy, wide=True),
        "accel_x_q8": q8(ax, wide=True),
        "accel_y_q8": q8(ay, wide=True),
        "remove_time": integer(ctrl.get("removetime"), -1),
        "spr_priority": integer(ctrl.get("sprpriority"), 0),
        "postype": postype,
        "ownpal": integer(ctrl.get("ownpal"), 0),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
        "bind_time": integer(ctrl.get("bindtime"), 0),
        "remove_on_gethit": integer(ctrl.get("removeongethit"), 0),
        "remove_on_state_change": integer(
            ctrl.get("removeonchangestate"), 0),
        "facing": 1 if integer(ctrl.get("facing"), 1) >= 0 else -1,
        "vfacing": 1 if integer(ctrl.get("vfacing"), 1) >= 0 else -1,
        "scale_x_q8": q8(sx),
        "scale_y_q8": q8(sy),
        "trans_mode": trans_map[trans_text],
        "alpha": alpha_value,
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_EXPLOD",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": explod_index,
        "value1": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    return controller, explod


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
    sd = state.statedef

    state_type = STATE_TYPE.get(
        (sd.get("type", "U") or "U").strip().upper()
    )
    move_type = MOVE_TYPE.get(
        (sd.get("movetype", "U") or "U").strip().upper()
    )
    physics = PHYSICS.get(
        (sd.get("physics", "N") or "N").strip().upper()
    )
    if state_type is None or move_type is None or physics is None:
        raise ValueError(f"state {state.number}: unsupported Statedef type")

    vx, vy, velset_x_expr, velset_y_expr = pair_runtime_expr(
        sd.get("velset"), 0, 0)
    has_velset = sd.get("velset") is not None

    hitdefs: list[dict] = []
    projectile_hitdefs: list[dict] = []
    direct_hitdef_count = 0
    sounds: list[dict] = []
    controllers: list[dict] = []
    helpers: list[dict] = []
    explods: list[dict] = []
    projectiles: list[dict] = []
    projectile_mods: list[dict] = []
    reversals: list[dict] = []
    hitoverrides: list[dict] = []
    open_reversal: dict | None = None
    unsupported: list[str] = []
    assert_special_flags = 0

    def attach_target_query_selector(
        controller: dict,
        section: Section,
    ) -> dict:
        if controller.get("trigger_kind") != "IK_CNS_TRIGGER_NUM_TARGET_QUERY":
            return controller
        selector = -1
        for expr in section.all("trigger1"):
            match = re.search(
                r"NumTarget\s*\(\s*(-?\d+)\s*\)",
                expr,
                flags=re.I,
            )
            if match:
                selector = int(match.group(1))
                break
        controller["trigger_aux"] = selector
        return controller

    for ctrl in state.controllers:
        folded = fold_self_anim_exist(ctrl)
        if folded is None:
            continue
        ctrl = folded
        ctype = (ctrl.get("type", "") or "").strip().lower()

        # MUGEN's Null controller deliberately disables the controller body.
        # It has no runtime effect and must not block strict conversion.
        if ctype == "null":
            continue

        if ctype == "hitdef":
            (
                trig_kind,
                trig_value,
                trig2_kind,
                trig2_value,
                p2_dist_op,
                p2_dist_x,
                trigger_expr,
                trigger2_expr,
            ) = hitdef_trigger(ctrl)

            damage_text = ctrl.get("damage") or "0,0"
            alt_damage = -1
            alt_damage_prev_state = -32768
            damage_expr = re.fullmatch(
                r"\s*(-?\d+)\s*\+\s*"
                r"\(\s*prevstateno\s*=\s*(-?\d+)\s*\)"
                r"\s*\*\s*(-?\d+)\s*,\s*(-?\d+)\s*",
                damage_text,
                flags=re.I,
            )
            if damage_expr:
                damage = int(damage_expr.group(1))
                alt_damage_prev_state = int(damage_expr.group(2))
                alt_damage = damage + int(damage_expr.group(3))
                guard_damage = int(damage_expr.group(4))
                damage_runtime_expr = None
                guard_damage_runtime_expr = None
            else:
                (damage, guard_damage, damage_runtime_expr,
                 guard_damage_runtime_expr) = pair_integer_runtime_expr(
                    damage_text, 0, 0)
            (pause1, pause2, pause_p1_expr,
             pause_p2_expr) = pair_integer_runtime_expr(
                ctrl.get("pausetime"), 0, 0)
            gx, gy, ground_vx_expr, ground_vy_expr = pair_runtime_expr(
                ctrl.get("ground.velocity"), 0, 0)
            if ctrl.get("air.velocity") is None:
                ax, ay = gx, gy
                air_vx_expr, air_vy_expr = ground_vx_expr, ground_vy_expr
            else:
                ax, ay, air_vx_expr, air_vy_expr = pair_runtime_expr(
                    ctrl.get("air.velocity"), gx, gy)
            ground_slide_time, ground_slide_time_expr = \
                integer_or_runtime_expr(ctrl.get("ground.slidetime"), 0)
            ground_hit_time, ground_hit_time_expr = \
                integer_or_runtime_expr(ctrl.get("ground.hittime"), 0)
            if ctrl.get("air.hittime") is not None:
                air_hit_time, air_hit_time_expr = integer_or_runtime_expr(
                    ctrl.get("air.hittime"), ground_hit_time)
            else:
                air_hit_time, air_hit_time_expr = (
                    ground_hit_time, ground_hit_time_expr)
            guard_times_values, guard_times_exprs = guard_times_runtime(
                ctrl, ground_slide_time, ground_slide_time_expr)
            guardx, guardx_expr = number_or_runtime_expr(
                ctrl.get("guard.velocity"), gx)
            agx, agy = pair(
                ctrl.get("airguard.velocity"),
                ax * 1.5,
                ay / 2.0,
            )
            fall_x_text = ctrl.get("fall.xvelocity")
            fall_x, fall_x_expr = number_or_runtime_expr(fall_x_text, 0)
            fall_y, fall_y_expr = number_or_runtime_expr(
                ctrl.get("fall.yvelocity"), -4.5)
            down_x, down_y = pair(ctrl.get("down.velocity"), ax, ay)
            down_hit_time = integer(ctrl.get("down.hittime"), 0)
            (sparkx, sparky, spark2y, sparkx_expr, sparky_expr,
             spark2y_expr) = spark_pair_runtime(ctrl.get("sparkxy"))
            hs_group, hs_item, hs_group_expr, hs_item_expr = \
                sound_pair_runtime(ctrl.get("hitsound"))
            gs_group, gs_item, gs_group_expr, gs_item_expr = \
                sound_pair_runtime(ctrl.get("guardsound"))
            recover_text = ctrl.get("fall.recover")
            if recover_text is None:
                recover_text = ctrl.get("air.recover")
            fall_recover, fall_recover_expr = integer_or_runtime_expr(
                recover_text, 1)
            fall_recover_time, fall_recover_time_expr = \
                integer_or_runtime_expr(ctrl.get("fall.recovertime"), 4)
            fall_damage, fall_damage_expr = integer_or_runtime_expr(
                ctrl.get("fall.damage"), 0)
            envshake_time, envshake_time_expr = integer_or_runtime_expr(
                ctrl.get("envshake.time"), 0)
            envshake_ampl, envshake_ampl_expr = integer_or_runtime_expr(
                ctrl.get("envshake.ampl"), 0)
            envshake_freq, envshake_freq_expr = integer_or_runtime_expr(
                ctrl.get("envshake.freq"), 60)
            fall_envshake_time, fall_envshake_time_expr = \
                integer_or_runtime_expr(ctrl.get("fall.envshake.time"), 0)
            fall_envshake_ampl, fall_envshake_ampl_expr = \
                integer_or_runtime_expr(ctrl.get("fall.envshake.ampl"), 0)
            fall_envshake_freq, fall_envshake_freq_expr = \
                integer_or_runtime_expr(ctrl.get("fall.envshake.freq"), 60)
            cornerpush_veloff, cornerpush_veloff_expr = \
                number_or_runtime_expr(
                    ctrl.get("ground.cornerpush.veloff"), 0)
            spark_no_text = ctrl.get("sparkno")
            guard_spark_no_text = ctrl.get("guard.sparkno")
            if spark_no_text and spark_no_text[:1].casefold() in {"s", "f"}:
                spark_no_text = spark_no_text[1:]
            if guard_spark_no_text and guard_spark_no_text[:1].casefold() in {"s", "f"}:
                guard_spark_no_text = guard_spark_no_text[1:]
            spark_no, spark_no_expr = integer_or_runtime_expr(
                spark_no_text, default_spark_no)
            guard_spark_no, guard_spark_no_expr = integer_or_runtime_expr(
                guard_spark_no_text, default_guard_spark_no)

            flags: list[str] = []
            fall_flag, fall_flag_expr = integer_or_runtime_expr(
                ctrl.get("fall"), 0)
            air_fall_flag, air_fall_flag_expr = integer_or_runtime_expr(
                ctrl.get("air.fall"), 0)
            if fall_flag:
                flags.append("IK_CNS_HITDEF_FALL")
            if air_fall_flag:
                flags.append("IK_CNS_HITDEF_AIR_FALL")
            if integer(ctrl.get("forcestand"), 0):
                flags.append("IK_CNS_HITDEF_FORCE_STAND")
            if integer(ctrl.get("forcenofall"), 0):
                flags.append("IK_CNS_HITDEF_FORCE_NO_FALL")
            attr_parts = [p.strip().upper() for p in (ctrl.get("attr") or "").split(",")]
            if len(attr_parts) > 1 and attr_parts[1].endswith("T"):
                flags.append("IK_CNS_HITDEF_THROW")
            air_juggle, air_juggle_expr = integer_or_runtime_expr(
                ctrl.get("air.juggle"), 0)

            hitdefs.append(
                {
                    "state_number": state.number,
                    "trigger_kind": trig_kind,
                    "trigger_value": trig_value,
                    "trigger2_kind": trig2_kind,
                    "trigger2_value": trig2_value,
                    "_trigger_expr": trigger_expr,
                    "_trigger2_expr": trigger2_expr,
                    "_air_juggle_expr": air_juggle_expr,
                    "_fall_expr": fall_flag_expr,
                    "_air_fall_expr": air_fall_flag_expr,
                    "_ground_cornerpush_veloff_expr": cornerpush_veloff_expr,
                    "_guard_velocity_x_expr": guardx_expr,
                    "_fall_damage_expr": fall_damage_expr,
                    "_envshake_time_expr": envshake_time_expr,
                    "_envshake_ampl_expr": envshake_ampl_expr,
                    "_envshake_freq_expr": envshake_freq_expr,
                    "_fall_envshake_time_expr": fall_envshake_time_expr,
                    "_fall_envshake_ampl_expr": fall_envshake_ampl_expr,
                    "_fall_envshake_freq_expr": fall_envshake_freq_expr,
                    "_damage_expr": damage_runtime_expr,
                    "_guard_damage_expr": guard_damage_runtime_expr,
                    "_pause_p1_expr": pause_p1_expr,
                    "_pause_p2_expr": pause_p2_expr,
                    "_spark_x_expr": sparkx_expr,
                    "_spark_y_expr": sparky_expr,
                    "_trigger2_spark_y_expr": spark2y_expr,
                    "_hit_sound_group_expr": hs_group_expr,
                    "_hit_sound_item_expr": hs_item_expr,
                    "_guard_sound_group_expr": gs_group_expr,
                    "_guard_sound_item_expr": gs_item_expr,
                    "_fall_recover_expr": fall_recover_expr,
                    "_fall_recover_time_expr": fall_recover_time_expr,
                    "_spark_no_expr": spark_no_expr,
                    "_guard_spark_no_expr": guard_spark_no_expr,
                    "_fall_x_velocity_expr": fall_x_expr,
                    "_fall_y_velocity_expr": fall_y_expr,
                    "_ground_velocity_x_expr": ground_vx_expr,
                    "_ground_velocity_y_expr": ground_vy_expr,
                    "_air_velocity_x_expr": air_vx_expr,
                    "_air_velocity_y_expr": air_vy_expr,
                    "_ground_slide_time_expr": ground_slide_time_expr,
                    "_ground_hit_time_expr": ground_hit_time_expr,
                    "_air_hit_time_expr": air_hit_time_expr,
                    "_guard_hit_time_expr": guard_times_exprs[0],
                    "_guard_slide_time_expr": guard_times_exprs[1],
                    "_guard_ctrl_time_expr": guard_times_exprs[2],
                    "has_trigger2": int(trig2_kind != 255),
                    "damage": int(damage),
                    "guard_damage": int(guard_damage),
                    "priority": integer(
                        (ctrl.get("priority") or "4").split(",", 1)[0],
                        4,
                    ),
                    "priority_type": priority_type_code(ctrl.get("priority")),
                    "pause_p1": int(pause1),
                    "pause_p2": int(pause2),
                    "ground_type": GROUND_TYPE.get(
                        (
                            ctrl.get("ground.type", "normal") or "normal"
                        ).strip().lower(),
                        "IK_CNS_GROUND_NORMAL",
                    ),
                    "ground_slide_time": ground_slide_time,
                    "ground_hit_time": ground_hit_time,
                    "air_hit_time": air_hit_time,
                    "ground_velocity_x_q8": q8(gx),
                    "ground_velocity_y_q8": q8(gy),
                    "air_velocity_x_q8": q8(ax),
                    "air_velocity_y_q8": q8(ay),
                    "spark_no": spark_no,
                    "guard_spark_no": guard_spark_no,
                    "spark_x": int(sparkx),
                    "spark_y": int(sparky),
                    "trigger2_spark_y": int(spark2y),
                    "hit_sound_group": hs_group,
                    "hit_sound_item": hs_item,
                    "guard_sound_group": gs_group,
                    "guard_sound_item": gs_item,
                    "flags": " | ".join(flags) if flags else "0u",
                    "guard_flags": guard_mask(ctrl.get("guardflag")),
                    "guard_kill": integer(ctrl.get("guard.kill"), 1),
                    "hit_flags": hit_mask(ctrl.get("hitflag")),
                    "guard_slide_time": guard_times_values[1],
                    "guard_hit_time": guard_times_values[0],
                    "guard_ctrl_time": guard_times_values[2],
                    "guard_velocity_x_q8": q8(guardx),
                    "air_guard_velocity_x_q8": q8(agx),
                    "air_guard_velocity_y_q8": q8(agy),
                    "anim_type": anim_type_code(ctrl.get("animtype")),
                    "air_anim_type": anim_type_code(
                        ctrl.get("air.animtype", ctrl.get("animtype", "light"))
                    ),
                    "fall_anim_type": fall_anim_type_code(ctrl),
                    "fall_x_velocity_q8": q8(fall_x),
                    "fall_y_velocity_q8": q8(fall_y),
                    "fall_x_velocity_set": int(fall_x_text is not None),
                    "fall_recover": fall_recover,
                    "fall_recover_time": fall_recover_time,
                    "down_hit_time": down_hit_time,
                    "down_velocity_x_q8": q8(down_x),
                    "down_velocity_y_q8": q8(down_y),
                    "down_bounce": integer(ctrl.get("down.bounce"), 0),
                    "air_juggle": air_juggle,
                    "p1_state_no": integer(ctrl.get("p1stateno"), -1),
                    "p2_state_no": integer(ctrl.get("p2stateno"), -1),
                    "guard_dist": integer(ctrl.get("guard.dist"), -1),
                    "p1_facing": integer(ctrl.get("p1facing"), 0),
                    "p2_facing": integer(ctrl.get("p2facing"), 0),
                    "p1_spr_priority": integer(ctrl.get("p1sprpriority"), -128),
                    "p2_body_dist_op": p2_dist_op,
                    "p2_body_dist_x": p2_dist_x,
                    "alt_damage": alt_damage,
                    "alt_damage_prev_state": alt_damage_prev_state,
                    "yaccel_q8": q8(number(ctrl.get("yaccel"), .35)),
                    "yaccel_q16": q16(number(ctrl.get("yaccel"), .35)),
                    **power_fields(ctrl),
                    **dist_fields(ctrl),
                    "has_alt_damage": int(damage_expr is not None),
                    "ground_cornerpush_veloff_q8": q8(cornerpush_veloff),
                    "attack_attr_mask": attack_attr_mask(
                        attr_parts[1] if len(attr_parts) > 1 else ""
                    ),
                    "fall_damage": fall_damage,
                    "envshake_time": envshake_time,
                    "envshake_ampl": envshake_ampl,
                    "envshake_freq": envshake_freq,
                    "fall_envshake_time": fall_envshake_time,
                    "fall_envshake_ampl": fall_envshake_ampl,
                    "fall_envshake_freq": fall_envshake_freq,
                    "id": integer(ctrl.get("id"), 0),
                    "chain_id": integer(ctrl.get("chainid"), -1),
                    "no_chain_id": integer(
                        (ctrl.get("nochainid") or "-1").split(",", 1)[0],
                        -1,
                    ),
                    "no_chain_id2": integer(
                        (ctrl.get("nochainid") or "-1,-1").split(",", 1)[1]
                        if "," in (ctrl.get("nochainid") or "")
                        else "-1",
                        -1,
                    ),
                }
            )
            direct_hitdef_count += 1

        elif ctype == "reversaldef":
            attr = (ctrl.get("reversal.attr") or "").strip()
            if attr:
                if open_reversal is not None:
                    raise ValueError(
                        f"state {state.number}: overlapping ReversalDef windows"
                    )
                parts = [p.strip().upper() for p in attr.split(",")]
                if len(parts) < 2:
                    unsupported.append("reversaldef")
                    continue
                incoming_attr_mask = attack_attr_mask(parts[1])
                if incoming_attr_mask == "0u":
                    unsupported.append("reversaldef")
                    continue
                triggers = ctrl.all("trigger1")
                if len(triggers) != 1:
                    unsupported.append("reversaldef")
                    continue
                start = re.fullmatch(
                    r"Time\s*=\s*(\d+)",
                    _strip_outer_parens(triggers[0]),
                    flags=re.I,
                )
                if not start:
                    unsupported.append("reversaldef")
                    continue
                pause1, pause2 = pair(ctrl.get("pausetime"), 0, 0)
                sparkx, sparky, _ = spark_pair(ctrl.get("sparkxy"))
                hs = sound_pair(ctrl.get("hitsound"))
                open_reversal = {
                    "state_number": state.number,
                    "start_time": int(start.group(1)),
                    "end_time": 65535,
                    "attacker_state_mask": reversal_state_mask(parts[0]),
                    "incoming_attr_mask": incoming_attr_mask,
                    "pause_p1": int(pause1),
                    "pause_p2": int(pause2),
                    "spark_no": integer(ctrl.get("sparkno"), -1),
                    "spark_x": int(sparkx),
                    "spark_y": int(sparky),
                    "hit_sound_group": hs[0],
                    "hit_sound_item": hs[1],
                    "p1_state_no": integer(ctrl.get("p1stateno"), -1),
                    "p1_spr_priority": integer(
                        ctrl.get("p1sprpriority"), -128
                    ),
                    "p2_spr_priority": integer(
                        ctrl.get("p2sprpriority"), -128
                    ),
                }
            elif open_reversal is not None:
                end_time: int | None = None
                trigger2 = ctrl.all("trigger2")
                # Prefer an explicit OR stop branch when present. KFM state
                # 1300 has a deliberately odd trigger1 conjunction plus
                # trigger2 = Time = 8; the trigger2 branch is the deterministic
                # end of its authored reversal window.
                for expr in trigger2:
                    m = re.fullmatch(
                        r"Time\s*=\s*(\d+)",
                        _strip_outer_parens(expr),
                        flags=re.I,
                    )
                    if m:
                        end_time = int(m.group(1))
                        break
                if end_time is None:
                    for expr in ctrl.all("trigger1"):
                        m = re.fullmatch(
                            r"Time\s*=\s*(\d+)",
                            _strip_outer_parens(expr),
                            flags=re.I,
                        )
                        if m:
                            end_time = int(m.group(1))
                            break
                if end_time is None:
                    unsupported.append("reversaldef")
                else:
                    open_reversal["end_time"] = end_time
                    reversals.append(open_reversal)
                open_reversal = None

        elif ctype == "hitoverride":
            raw_attr = (ctrl.get("attr") or "").strip()
            if not raw_attr:
                continue
            parts = [p.strip().upper() for p in raw_attr.split(",")]
            if len(parts) < 2:
                unsupported.append("hitoverride")
                continue
            self_mask = no_hit_by_state_mask(parts[0])
            incoming_mask = attack_attr_mask(parts[1])
            if self_mask == "0u" or incoming_mask == "0u":
                unsupported.append("hitoverride")
                continue

            triggers = ctrl.all("trigger1")
            if len(triggers) != 1:
                unsupported.append("hitoverride")
                continue
            expr = _strip_outer_parens(triggers[0])
            m_eq = re.fullmatch(r"Time\s*=\s*(\d+)", expr, flags=re.I)
            m_lt = re.fullmatch(r"Time\s*<\s*(\d+)", expr, flags=re.I)
            if m_eq:
                start_time = int(m_eq.group(1))
                end_time = start_time + max(
                    1, integer(ctrl.get("time"), 1)
                )
            elif m_lt:
                start_time = 0
                end_time = int(m_lt.group(1))
            else:
                unsupported.append("hitoverride")
                continue

            hitoverrides.append({
                "state_number": state.number,
                "start_time": start_time,
                "end_time": end_time,
                "self_state_mask": self_mask,
                "incoming_attr_mask": incoming_mask,
                "target_state": integer(ctrl.get("stateno"), -1),
            })

        elif ctype == "playsnd":
            sound_parts = _split_top_level(ctrl.get("value") or "")
            if len(sound_parts) != 2:
                raise ValueError(
                    f"expected sound group,item, got {ctrl.get('value')!r}")
            group_text = sound_parts[0].strip()
            if group_text[:1].casefold() in {"s", "f"}:
                group_text = group_text[1:]
            sound_group, group_expr = integer_or_runtime_expr(group_text, 0)
            item, item_expr = integer_or_runtime_expr(sound_parts[1], 0)
            triggerall = [f"({expr})" for expr in ctrl.all("triggerall")]
            has_trigger_group = False
            for trigger_index in range(1, 9):
                trigger_group = ctrl.all(f"trigger{trigger_index}")
                if not trigger_group:
                    continue
                has_trigger_group = True
                trigger_exprs = triggerall + [
                    f"({expr})" for expr in trigger_group
                ]
                try:
                    if len(trigger_exprs) == 1:
                        probe = Section(
                            ctrl.name, [("trigger1", trigger_exprs[0])]
                        )
                        trig_kind, trig_value, _ = simple_trigger(probe)
                        trigger_expr = None
                    else:
                        raise ValueError("combined trigger expression")
                except ValueError:
                    expression_text = " && ".join(trigger_exprs) or "1"
                    trigger_expr = compile_cns_expr(
                        expression_text, q16=True)
                    trig_kind, trig_value = "IK_CNS_TRIGGER_ALWAYS", 0
                sounds.append(
                    {
                        "state_number": state.number,
                        "trigger_kind": trig_kind,
                        "trigger_value": trig_value,
                        "group": sound_group,
                        "item": item,
                        "_group_expr": group_expr,
                        "_item_expr": item_expr,
                        "_trigger_expr": trigger_expr,
                    }
                )
            if not has_trigger_group:
                sounds.append({
                    "state_number": state.number,
                    "trigger_kind": "IK_CNS_TRIGGER_ALWAYS",
                    "trigger_value": 0,
                    "group": sound_group,
                    "item": item,
                    "_group_expr": group_expr,
                    "_item_expr": item_expr,
                    "_trigger_expr": (
                        compile_cns_expr(
                            " && ".join(triggerall), q16=True)
                        if triggerall else None
                    ),
                })

        elif ctype == "helper":
            try:
                compiled_helper = compile_helper_controller(
                    state.number, ctrl, helper_ofs + len(helpers)
                )
            except ValueError:
                compiled_helper = None
            if compiled_helper is not None:
                controller, helper = compiled_helper
                controllers.append(
                    attach_target_query_selector(controller, ctrl)
                )
                helpers.append(helper)
            else:
                unsupported.append(ctype)

        elif ctype == "explod":
            try:
                compiled_explod = compile_explod_controller(
                    state.number, ctrl, explod_ofs + len(explods)
                )
            except ValueError:
                compiled_explod = None
            if compiled_explod is not None:
                controller, explod = compiled_explod
                controllers.append(
                    attach_target_query_selector(controller, ctrl)
                )
                explods.append(explod)
            else:
                unsupported.append(ctype)

        elif ctype == "projectile":
            try:
                compiled_projectile = compile_projectile_controller(
                    state.number,
                    ctrl,
                    projectile_ofs + len(projectiles),
                    -1,
                    default_spark_no,
                    default_guard_spark_no,
                )
            except ValueError:
                compiled_projectile = None
            if compiled_projectile is not None:
                controller, projectile, projectile_hitdef = compiled_projectile
                controllers.append(
                    attach_target_query_selector(controller, ctrl)
                )
                projectiles.append(projectile)
                projectile_hitdefs.append(projectile_hitdef)
            else:
                unsupported.append(ctype)

        elif ctype == "modifyprojectile":
            try:
                compiled_mod = compile_modify_projectile_controller(
                    state.number,
                    ctrl,
                    projectile_mod_ofs + len(projectile_mods),
                )
            except ValueError:
                compiled_mod = None
            if compiled_mod is not None:
                controller, projectile_mod = compiled_mod
                controllers.append(
                    attach_target_query_selector(controller, ctrl)
                )
                projectile_mods.append(projectile_mod)
            else:
                unsupported.append(ctype)

        elif ctype == "assertspecial":
            flag = (ctrl.get("flag") or "").strip().casefold()
            trigger_lines = [
                value.strip() for key, value in ctrl.values
                if key.casefold().startswith("trigger")
            ]
            if flag in {"nowalk", "noautoturn"} and trigger_lines and all(
                value == "1" for value in trigger_lines
            ) and not ctrl.all("triggerall"):
                assert_special_flags |= (
                    1 if flag == "nowalk" else 2
                )
            else:
                unsupported.append(ctype)

        else:
            try:
                compiled = compile_runtime_controller(state.number, ctrl)
            except ValueError:
                compiled = None

            if compiled is not None:
                if ctrl.runtime_trigger_expr is not None:
                    compiled["trigger_expr"] = ctrl.runtime_trigger_expr
                if ctrl.runtime_value0_expr is not None:
                    compiled["value0_expr"] = ctrl.runtime_value0_expr
                if ctrl.runtime_value1_expr is not None:
                    compiled["value1_expr"] = ctrl.runtime_value1_expr
                controllers.append(
                    attach_target_query_selector(compiled, ctrl)
                )
                if ctype == "superpause" and ctrl.get("sound") is not None:
                    group, item, group_expr, item_expr = sound_pair_runtime(
                        ctrl.get("sound"))
                    sounds.append({
                        "state_number": state.number,
                        "trigger_kind": compiled["trigger_kind"],
                        "trigger_value": compiled["trigger_value"],
                        "group": group,
                        "item": item,
                        "_group_expr": group_expr,
                        "_item_expr": item_expr,
                    })
            elif ctype:
                unsupported.append(ctype)

    if open_reversal is not None:
        reversals.append(open_reversal)

    if len(hitdefs) > 32:
        raise ValueError(
            f"state {state.number}: more than 32 HitDefs are not supported"
        )

    for projectile_index, projectile in enumerate(projectiles):
        projectile["hitdef_global"] = (
            hitdef_ofs + len(hitdefs) + projectile_index
        )
    hitdefs.extend(projectile_hitdefs)

    power_add_expr = dynamic_power_add_expr(sd.get("poweradd"))
    juggle_expr = dynamic_power_add_expr(sd.get("juggle"))
    unsupported_state_fields: list[str] = []
    if sd.get("poweradd") is not None and power_add_expr is None:
        try:
            power_add = eval_int(sd.get("poweradd"), 0)
        except ValueError:
            if STRICT_CONVERSION:
                raise
            power_add = 0
            unsupported_state_fields.append("statedef.poweradd")
    else:
        power_add = 0 if power_add_expr else eval_int(sd.get("poweradd"), 0)
    if sd.get("juggle") is not None and juggle_expr is None:
        try:
            juggle_value = eval_int(sd.get("juggle"), 0)
        except ValueError:
            if STRICT_CONVERSION:
                raise
            juggle_value = 0
            unsupported_state_fields.append("statedef.juggle")
    else:
        juggle_value = 0 if juggle_expr else eval_int(sd.get("juggle"), 0)

    anim_expr = None
    try:
        anim_no = eval_int(sd.get("anim"), -1)
    except ValueError:
        if STRICT_CONVERSION:
            anim_expr = compile_cns_expr(sd.get("anim") or "-1")
            anim_no = -1
        else:
            anim_no = -1
            unsupported_state_fields.append("statedef.anim")

    state_row = {
        "number": state.number,
        "anim": anim_no,
        "anim_expr": anim_expr,
        "velset_x_expr": velset_x_expr,
        "velset_y_expr": velset_y_expr,
        "power_add": power_add,
        "power_add_expr": power_add_expr,
        "velset_x_q8": q8(vx),
        "velset_y_q8": q8(vy),
        "state_type": state_type,
        "move_type": move_type,
        "physics": physics,
        "ctrl": eval_int(sd.get("ctrl"), 0),
        "spr_priority": eval_int(sd.get("sprpriority"), 0),
        "has_velset": int(has_velset),
        "hitdef_ofs": hitdef_ofs,
        "hitdef_count": direct_hitdef_count,
        "playsnd_ofs": sound_ofs,
        "playsnd_count": len(sounds),
        "controller_ofs": controller_ofs,
        "controller_count": len(controllers),
        "juggle": juggle_value,
        "juggle_expr": juggle_expr,
        "has_juggle": int(sd.get("juggle") is not None),
        "owns_air_accel": int(any(
            c["type"] == "IK_CNS_CTRL_VEL_ADD" and
            "IK_CNS_CTRL_AXIS_Y" in c["flags"]
            for c in controllers
        )),
        "hitdef_persist": eval_int(sd.get("hitdefpersist"), 0),
        "hitcount_persist": eval_int(sd.get("hitcountpersist"), 0),
        "reversal_ofs": 0,
        "reversal_count": len(reversals),
        "hitoverride_ofs": 0,
        "hitoverride_count": len(hitoverrides),
        "assert_special_flags": (
            " | ".join(
                name for bit, name in (
                    (1, "IK_CNS_STATE_ASSERT_NO_WALK"),
                    (2, "IK_CNS_STATE_ASSERT_NO_AUTO_TURN"),
                ) if assert_special_flags & bit
            ) or "0u"
        ),
        "unsupported_controllers": sorted(
            set(unsupported + unsupported_state_fields)),
    }

    return (
        state_row, hitdefs, sounds, controllers, helpers, explods,
        projectiles, projectile_mods, reversals, hitoverrides
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
