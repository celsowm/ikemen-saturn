"""Parse literal CNS values and convert fixed-point asset fields."""
from __future__ import annotations

import re

Q8 = 256


def number(text: str | None, default: float = 0.0) -> float:
    if text is None:
        return default
    value = text.strip()
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


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            redirect_prefix = re.search(
                r"\b(?:parent|root|p2|enemy)\s*$|"
                r"\bplayerid\s*\(.*\)\s*$",
                text[start:index], re.I | re.S)
            redirected_field = re.match(
                r"\s*(?:var|sysvar|fvar|sysfvar|numexplod|pos|vel|"
                r"stateno|statetype|movetype)\b",
                text[index + 1:], re.I)
            if redirect_prefix and redirected_field:
                continue
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def pair(
    text: str | None,
    default_x: float = 0.0,
    default_y: float = 0.0,
) -> tuple[float, float]:
    if text is None:
        return default_x, default_y
    parts = split_top_level(text)
    if len(parts) == 1:
        return number(parts[0]), default_y
    if len(parts) in (2, 3):
        return number(parts[0]), number(parts[1])
    raise ValueError(f"expected scalar or pair, got {text!r}")


def q8(value: float, wide: bool = False) -> int:
    result = int(round(value * Q8))
    low, high = (-(1 << 31), (1 << 31) - 1) if wide else (-32768, 32767)
    if not low <= result <= high:
        raise ValueError(f"Q8.8 overflow for {value}")
    return result


def q16(value: float) -> int:
    result = int(round(value * 65536))
    if not -(1 << 31) <= result < (1 << 31):
        raise ValueError(f"Q16.16 overflow for {value}")
    return result


def anim_type_code(text: str | None) -> int:
    value = (text or "light").strip().lower()
    return {
        "light": 0, "medium": 1, "med": 1, "hard": 2, "heavy": 2,
        "back": 3, "up": 4, "diagup": 5, "diag-up": 5,
    }.get(value, 0)


def fall_anim_type_code(ctrl: dict) -> int:
    """Resolve FallAnimType using the upstream defaulting rules."""
    if ctrl.get("fall.animtype") is not None:
        return anim_type_code(ctrl.get("fall.animtype"))
    air = anim_type_code(ctrl.get("air.animtype") or ctrl.get("animtype") or "light")
    return air if air >= 4 else 3
