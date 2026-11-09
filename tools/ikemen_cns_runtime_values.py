"""Runtime expression and controller value lowering for CNS conversion."""
from __future__ import annotations

import re

_SELF_ANIM_TERM = re.compile(r"(!?)\s*SelfAnimExist\s*\(\s*(\d+)\s*\)", re.I)
_SERVICES: dict | None = None

try:
    from .ikemen_cns_expr import _ExprParser, compile_cns_expr as compile_expression
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_expr import _ExprParser, compile_cns_expr as compile_expression


def configure(services: dict) -> None:
    """Bind per-conversion settings and shared constant tables."""
    global _SERVICES
    _SERVICES = services
    for name in ("_split_top_level", "number", "integer", "q8", "Section"):
        globals()[name] = services[name]


def compile_cns_expr(text: str, q16: bool = False) -> list[dict]:
    return compile_expression(
        text,
        q16,
        command_ids=_SERVICES["COMMAND_IDS"],
        localcoord_x=_SERVICES["LOCALCOORD_X"],
        const_values=_SERVICES["CONST_VALUES"],
        self_anims=_SERVICES["SELF_ANIMS"],
        character_author=_SERVICES.get("CHARACTER_AUTHOR"),
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
    self_anims = _SERVICES["SELF_ANIMS"]
    if self_anims is not None:
        text = _SELF_ANIM_TERM.sub(
            lambda match: str(
                int(int(match.group(2)) in self_anims) ^
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


def pair_static_expr(
    text: str | None,
    default_x: float = 0.0,
    default_y: float = 0.0,
) -> tuple[float, float]:
    """Evaluate a numeric pair containing only compile-time expressions."""
    if text is None:
        return default_x, default_y
    parts = _split_top_level(text)
    if len(parts) == 1:
        parts.append(str(default_y))
    if len(parts) not in (2, 3):
        raise ValueError(f"expected numeric value pair, got {text!r}")
    try:
        return _ExprParser(parts[0]).parse(), _ExprParser(parts[1]).parse()
    except ValueError as exc:
        raise ValueError(f"expected static numeric pair, got {text!r}: {exc}") from exc


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
        if _SERVICES["STRICT_CONVERSION"]:
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
        if _SERVICES["STRICT_CONVERSION"]:
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
                value, expression = number_or_runtime_expr(part, 0)
                field = f"{name}dist_{axis}"
                out[f"{field}_q8"] = q8(value)
                if expression is not None:
                    out[f"_{field}_expr"] = expression
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

