"""Normalize MUGEN-specific syntax before runtime CNS bytecode compilation."""
from __future__ import annotations

import math
import re

def character_name_hash(name: str) -> int:
    value = 2166136261
    for byte in name.casefold().encode("utf-8"):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value & 0x7fffffff



def _normalize_logical_operators(text: str) -> str:
    """Normalize MUGEN's single-character logical operators."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "|":
            output.append("||")
            index += 2 if text[index:index + 2] == "||" else 1
            continue
        if char == "&":
            output.append("&&")
            index += 2 if text[index:index + 2] == "&&" else 1
            continue
        output.append(char)
        index += 1
    return "".join(output)

def normalize_cns_expr(
    text: str,
    q16: bool = False,
    *,
    command_ids: dict[str, int] | None = None,
    localcoord_x: float = 320.0,
    const_values: dict[str, float] | None = None,
    self_anims: set[int] | None = None,
    character_author: str | None = None,
) -> str:
    def expand_state_range(match: re.Match[str]) -> str:
        field, operator, low, high = match.groups()
        field = field.lower()
        if operator == "=":
            return f"(({field}>={low}) && ({field}<={high}))"
        return f"(({field}<{low}) || ({field}>{high}))"

    def expand_interval(match: re.Match[str]) -> str:
        if re.search(
            r"\bhelper\s*\([^()]*\)\s*,\s*$",
            normalized[:match.start()], flags=re.I,
        ):
            return match.group(0)
        field, operator, opening, low, high, closing = match.groups()
        low_op = ">=" if opening == "[" else ">"
        high_op = "<=" if closing == "]" else "<"
        if operator in ("=", "=="):
            return (
                f"(({field}{low_op}{low}) && "
                f"({field}{high_op}{high}))"
            )
        outside_low_op = "<" if opening == "[" else "<="
        outside_high_op = ">" if closing == "]" else ">="
        return (
            f"(({field}{outside_low_op}{low}) || "
            f"({field}{outside_high_op}{high}))"
        )

    normalized = _normalize_logical_operators(text)
    def rounds_existed(match: re.Match[str]) -> str:
        if re.search(
            r"\b(?:p2|enemy|enemynear|target|parent|root)\s*,\s*$",
            normalized[:match.start()], flags=re.I,
        ):
            return match.group(0)
        return "(roundno > 1)"

    normalized = re.sub(
        r"\broundsexisted\b", rounds_existed, normalized, flags=re.I,
    )
    def stage_author(match: re.Match[str]) -> str:
        operator, author = match.groups()
        expression = f"stageauthoris({character_name_hash(author)})"
        return expression if operator != "!=" else f"!{expression}"

    normalized = re.sub(
        r"\bstagevar\s*\(\s*info\.author\s*\)\s*(==|!=|=)\s*"
        r"\"([^\"]*)\"",
        stage_author,
        normalized,
        flags=re.I,
    )
    def expand_time_mod(match: re.Match[str]) -> str:
        divisor = int(match.group(2))
        if divisor <= 0:
            raise ValueError("TimeMod divisor must be a positive integer")
        return f"((time % {divisor}) {match.group(1)} {match.group(3)})"

    normalized = re.sub(
        r"\btimemod\s*(==|!=|=)\s*(\d+)\s*,\s*(-?\d+)",
        expand_time_mod,
        normalized,
        flags=re.I,
    )
    def character_name(match: re.Match[str]) -> str:
        if re.search(
            r"\b(?:p2|enemy|enemynear|target|parent|root)\s*,\s*$",
            normalized[:match.start()], flags=re.I,
        ):
            return match.group(0)
        field, operator, name = match.groups()
        function = {
            "p1name": "p1nameis",
            "p2name": "p2nameis",
            "name": "nameis",
        }[field.casefold()]
        return f"{function}({character_name_hash(name)}) == {int(operator != '!=')}"

    normalized = re.sub(
        r"\b(p3name|p4name)\s*(==|!=|=)\s*\"([^\"]+)\"",
        lambda match: "1" if match.group(2) == "!=" else "0",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(p1name|p2name|name)\s*(==|!=|=)\s*\"([^\"]+)\"",
        character_name,
        normalized,
        flags=re.I,
    )
    def redirected_character_metadata(match: re.Match[str]) -> str:
        prefix, field, operator, value = match.groups()
        prefix = prefix.casefold()
        suffix = "authornameis" if field.casefold() == "authorname" else "nameis"
        prefix = {
            "p2": "p2", "enemy": "enemy", "enemynear": "enemynear",
            "target": "target", "parent": "parent", "root": "root",
        }[prefix]
        return (
            f"{prefix}{suffix}({character_name_hash(value)}) == "
            f"{int(operator != '!=')}"
        )

    normalized = re.sub(
        r"\b(p2|enemy|enemynear|target|parent|root)\s*,\s*"
        r"(name|authorname)\s*(==|!=|=)\s*\"([^\"]*)\"",
        redirected_character_metadata,
        normalized,
        flags=re.I,
    )
    if character_author is not None:
        normalized = re.sub(
            r"\bauthorname\s*(==|!=|=)\s*\"([^\"]*)\"",
            lambda match: str(
                (character_author.casefold() == match.group(2).casefold()) ^
                (match.group(1) == "!=")
            ),
            normalized,
            flags=re.I,
        )
    if self_anims is not None:
        normalized = expand_dynamic_self_anim_exist(normalized, self_anims)

    def expand_self_const(match: re.Match[str]) -> str:
        # A redirected Const belongs to that player/helper/target. Keep it in
        # the expression so runtime field loading can resolve the right CNS
        # asset instead of substituting the current character's value.
        prefix = normalized[:match.start()]
        if re.search(
            r"\b(?:p2|enemy|enemynear|target|parent|root)\s*,\s*$",
            prefix,
            flags=re.I,
        ):
            return match.group(0)
        name = match.group(1).casefold()
        if name in (const_values or {}):
            return str((const_values or {})[name])
        return match.group(0)

    normalized = re.sub(
        r"\bconst\s*\(\s*([a-z][a-z0-9_.]*)\s*\)",
        expand_self_const,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(p2|enemy|enemynear|target|parent|root)\s*,\s*alive\b",
        lambda match: f"({match.group(1)},life > 0)",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"\balive\b", "(life > 0)", normalized, flags=re.I)
    def const_720p(match: re.Match[str]) -> str:
        value = float(match.group(1)) * localcoord_x / 1280.0
        if not q16 and int(value) != value:
            raise ValueError(
                f"Const720p({match.group(1)}) is fractional in "
                f"localcoord.x={localcoord_x:g}; expression needs Q16 context")
        return str(int(value) if int(value) == value else value)

    normalized = re.sub(
        r"\bconst720p\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)",
        const_720p,
        normalized,
        flags=re.I,
    )
    def command_name(match: re.Match[str]) -> str:
        name = match.group(2)
        command_id = (command_ids or {}).get(name.casefold())
        if command_id is None:
            raise ValueError(
                f"command {name!r} has no matching --command-source entry")
        return f"command({command_id}) {match.group(1)} 1"

    normalized = re.sub(
        r"\bcommand\s*(=|!=|==)\s*\"([^\"]+)\"",
        command_name,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bfloor\s*\(\s*(\d+)\s*\*\s*ifelse\s*\(\s*"
        r"(.+?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
        r"(-?\d+(?:\.\d+)?)\s*\)\s*\)",
        lambda match: f"IfElse({match.group(2)},"
        f"{int(math.floor(int(match.group(1)) * float(match.group(3))))},"
        f"{int(math.floor(int(match.group(1)) * float(match.group(4))))})",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\bceil\s*\(\s*(\d+(?:\.\d+)?)\s*\*\s*"
        r"(parent|root|p2)\s*,\s*fvar\s*\(\s*(\d+)\s*\)"
        r"\s*\*\s*(\d+)\s*\)",
        lambda match: (
            f"Ceil({match.group(2)},FVar({match.group(3)})*"
            f"{int(round(float(match.group(1)) * int(match.group(4))))})"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelemno\s*\(\s*0\s*\)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"((animelem >= {match.group(2)}) && "
            f"(animelem <= {match.group(3)}))"
            if match.group(1) == "=" else
            f"((animelem < {match.group(2)}) || "
            f"(animelem > {match.group(3)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*=\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"((animelemtime({match.group(1)}) >= {match.group(2)}) && "
            f"(animelemtime({match.group(1)}) <= {match.group(3)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*(-?\d+)\b",
        lambda match: (
            f"animelemtime({match.group(1)}) = {match.group(2)}"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b((?:(?:p2|enemy|enemynear|parent|root)\s*,\s*)?"
        r"(?:stateno|p2stateno|prevstateno|anim))\s*(==|!=|=)\s*"
        r"([\[(])\s*(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(time|gametime)\s*(==|!=|=)\s*([\[(])\s*"
        r"(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(p2bodydist\s+x)\s*(==|!=|=)\s*([\[(])\s*"
        r"(-?\d+)\s*,\s*(-?\d+)\s*([\])])",
        expand_interval,
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b((?:(?:parent|root|p2)\s*,\s*)?"
        r"(?:var|sysvar|fvar)\s*\(\s*\d+\s*\))"
        r"\s*(!=|=)\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(gethitvar\s*\(\s*[a-z][a-z0-9_.]*\s*\))"
        r"\s*(!=|=)\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b(random(?:\s*%\s*\d+)?)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"\b([a-z][a-z0-9_]*)\s*(!=|=)\s*"
        r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
        lambda match: (
            f"(({match.group(1)} >= {match.group(3)}) && "
            f"({match.group(1)} <= {match.group(4)}))"
            if match.group(2) == "=" else
            f"(({match.group(1)} < {match.group(3)}) || "
            f"({match.group(1)} > {match.group(4)}))"
        ),
        normalized,
        flags=re.I,
    )
    state_types = {"u": 0, "s": 1, "c": 2, "a": 3, "l": 4}
    move_types = {"u": 0, "i": 1, "a": 2, "h": 3}
    for field in ("p2statetype", "statetype"):
        normalized = re.sub(
            rf"\b{field}\s*(=|!=)\s*([UCALS])\b",
            lambda match: f"{field}{match.group(1)}"
            f"{state_types[match.group(2).lower()]}",
            normalized,
            flags=re.I,
        )
    for field in ("p2movetype", "movetype"):
        normalized = re.sub(
            rf"\b{field}\s*(=|!=)\s*([UIAH])\b",
            lambda match: f"{field}{match.group(1)}"
            f"{move_types[match.group(2).lower()]}",
            normalized,
            flags=re.I,
        )
    normalized = re.sub(
        r"\banimelem\s*=\s*(\d+)\s*,\s*(<=|<|>=|>|=)\s*(-?\d+)",
        lambda match: (
            f"animelemtime({match.group(1)}) "
            f"{match.group(2)} {match.group(3)}"
        ),
        normalized,
        flags=re.I,
    )
    normalized = re.sub(
        r"(?<![\w.])(?:(p2|enemy|enemynear|parent|root|target)\s*,\s*)?"
        r"(anim|stateno|prevstateno|p2stateno|root_prevstateno|entityid)"
        r"\s*(==|!=|<=|>=|=|<|>)\s*(-?\d+)\b",
        lambda match: "rawcmp_{}_{}({})".format(
            (match.group(1).casefold() + "_" if match.group(1) else "") +
            match.group(2).casefold(),
            {"=": "eq", "==": "eq", "!=": "ne", "<": "lt",
             "<=": "le", ">": "gt", ">=": "ge"}[match.group(3)],
            match.group(4)),
        normalized,
        flags=re.I,
    )
    return normalized

def expand_dynamic_self_anim_exist(
    text: str, self_anims: set[int] | None
) -> str:
    """Fold literal SelfAnimExist queries; leave dynamic queries to runtime."""
    if self_anims is None:
        return text

    def terms_for_values(values: set[int], field: str) -> str:
        if not values:
            return "0"
        ordered = sorted(values)
        ranges: list[tuple[int, int]] = []
        start = previous = ordered[0]
        for value in ordered[1:]:
            if value == previous + 1:
                previous = value
                continue
            ranges.append((start, previous))
            start = previous = value
        ranges.append((start, previous))
        checks = [
            f"({field}>={low})" if low == high else
            f"(({field}>={low}) && ({field}<={high}))"
            for low, high in ranges
        ]
        return "(" + " || ".join(checks) + ")"

    def replace(match: re.Match[str]) -> str:
        negated, expression = match.groups()
        expression = re.sub(r"\s+", "", expression).casefold()
        fixed_action = re.fullmatch(r"\d+", expression)
        if not fixed_action:
            return match.group(0)
        result = "1" if int(fixed_action.group()) in self_anims else "0"
        return f"!({result})" if negated else result

    return re.sub(
        r"(!?)\s*SelfAnimExist\s*\(\s*([^()]+)\s*\)",
        replace,
        text,
        flags=re.I,
    )
