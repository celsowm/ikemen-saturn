"""Lower shared common-state definitions into the CNS runtime tables."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    from .ikemen_cns_common_motion import (
        LOCOMOTION_STATES, compile_motion_state,
    )
    from .ikemen_cns_common_guard import compile_guard_state
    from .ikemen_cns_common_hit import compile_hit_state
    from .ikemen_cns_common_gethit import compile_gethit_state
    from .ikemen_cns_common_fall import compile_fall_state
except ImportError:  # direct converter-script invocation
    from ikemen_cns_common_motion import (
        LOCOMOTION_STATES, compile_motion_state,
    )
    from ikemen_cns_common_guard import compile_guard_state
    from ikemen_cns_common_hit import compile_hit_state
    from ikemen_cns_common_gethit import compile_gethit_state
    from ikemen_cns_common_fall import compile_fall_state

try:
    from .ikemen_text import read_mugen_text
except ImportError:  # direct converter-script invocation
    from ikemen_text import read_mugen_text

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


def q8(value: float, wide: bool = False) -> int:
    result = int(round(value * Q8))
    low, high = (-(1 << 31), (1 << 31) - 1) if wide else (-32768, 32767)
    if not low <= result <= high:
        raise ValueError(f"Q8.8 overflow for {value}")
    return result


@dataclass
class ZssState:
    number: int
    metadata: dict[str, str]
    body: str


def parse_zss_states(path: Path) -> dict[int, ZssState]:
    text = read_mugen_text(path)
    # Support both ZSS ([StateDef N;...]) and CNS ([Statedef N]) formats
    matches = list(re.finditer(
        r"\[(?:StateDef|Statedef)\s+(-?\d+)(?:\s*;([^\]]*))?\]",
        text,
        flags=re.I,
    ))
    states: dict[int, ZssState] = {}
    for i, match in enumerate(matches):
        number_ = int(match.group(1))
        meta: dict[str, str] = {}
        metadata_text = (match.group(2) or "").strip()
        metadata_text = "\n".join(line.split("#", 1)[0]
                                  for line in metadata_text.splitlines())
        for part in metadata_text.split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            key, value = part.split(":", 1)
            meta[key.strip().lower()] = value.strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        states[number_] = ZssState(number_, meta, text[match.end():end])
    return states


def _common_ctrl(
    state_no: int,
    ctype: str,
    trigger_kind: str = "IK_CNS_TRIGGER_ALWAYS",
    trigger_value: int | str = 0,
    trigger_value2: int | str = 0,
    value0: int | str = 0,
    value1: int | str = 0,
    flags: str = "0u",
    value2: int | str = 0,
    value3: int | str = 0,
    value4: int | str = 0,
    value5: int | str = 0,
    value6: int | str = 0,
    value7: int | str = 0,
) -> dict:
    return {
        "state_number": state_no,
        "type": ctype,
        "trigger_kind": trigger_kind,
        "trigger_value": trigger_value,
        "trigger_value2": trigger_value2,
        "value0": value0,
        "value1": value1,
        "flags": flags,
        "value2": value2,
        "value3": value3,
        "value4": value4,
        "value5": value5,
        "value6": value6,
        "value7": value7,
    }


def compile_common_states(
    path: Path,
    selected: list[int],
    const: dict[str, int],
    controller_ofs: int,
    state_type_codes: dict[str, str],
    move_type_codes: dict[str, str],
    physics_codes: dict[str, str],
) -> tuple[list[dict], list[dict], dict[int, list[str]]]:
    """Lower explicitly supported shared common states to generic CNS ops.

    This is deliberately strict: only states whose ZSS semantics have an
    explicit lowering below are accepted. Source-state presence is verified,
    and deferred presentation-only behavior is surfaced in the JSON report.
    """
    source = parse_zss_states(path)
    missing = [n for n in selected if n not in source]
    if missing:
        raise ValueError(f"missing common Statedef(s): {missing}")

    supported = {
        0, 10, 11, 12, 20, 40, 45, 50, 51, 52, 100, 105, 106,
        120, 130, 131, 132, 140, 150, 151, 152, 153, 154, 155, 175,
        5000, 5001, 5010, 5011, 5020, 5030, 5035, 5040, 5050,
        5070, 5071, 5080, 5081, 5100, 5101, 5110, 5120, 5150,
        5200, 5201, 5210,
    }
    unsupported = sorted(set(selected) - supported)
    if unsupported:
        raise ValueError(
            "common1 states do not have a Saturn lowering yet: "
            f"{unsupported}"
        )

    def meta(n: int, key: str, default: str) -> str:
        return source[n].metadata.get(key, default).strip().upper()

    def state_row(
        n: int,
        anim: int,
        ctrl: int,
        land_state: int = 0,
        spr: int | None = None,
    ) -> dict:
        stype = state_type_codes.get(meta(n, "type", "U"))
        physics_value = physics_codes.get(meta(n, "physics", "N"))
        if stype is None or physics_value is None:
            raise ValueError(f"common state {n}: unsupported StateDef metadata")
        priority = (
            integer(source[n].metadata.get("sprpriority"), 0)
            if spr is None else spr
        )
        move_type_value = move_type_codes.get(meta(n, "movetype", "I"))
        if move_type_value is None:
            raise ValueError(f"common state {n}: unsupported move type")
        return {
            "number": n,
            "anim": anim,
            "power_add": 0,
            "power_add_expr": None,
            "juggle_expr": None,
            "velset_x_q8": 0,
            "velset_y_q8": 0,
            "state_type": stype,
            "move_type": move_type_value,
            "physics": physics_value,
            "ctrl": ctrl,
            "spr_priority": priority,
            "has_velset": 0,
            "hitdef_ofs": 0,
            "hitdef_count": 0,
            "playsnd_ofs": 0,
            "playsnd_count": 0,
            "controller_ofs": 0,
            "controller_count": 0,
            "land_state": land_state,
            "air_accel_q8": 0,
            "land_level_q8": 0,
            "air_motion_start": 0,
            "land_ctrl": 0,
            "juggle": 0,
            "has_juggle": 0,
            "owns_air_accel": 0,
            "assert_special_flags": "0u",
            "unsupported_controllers": [],
        }

    rows: list[dict] = []
    controllers: list[dict] = []
    deferred: dict[int, list[str]] = {}

    for n in selected:
        begin = controller_ofs + len(controllers)
        compiled = None
        for compiler in (
            compile_motion_state,
            compile_guard_state,
            compile_hit_state,
            compile_gethit_state,
            compile_fall_state,
        ):
            compiled = compiler(
                n, const, state_row, deferred, q8, _common_ctrl,
                LOCOMOTION_STATES,
            )
            if compiled is not None:
                break
        if compiled is None:
            raise ValueError(f"common state {n}: no state-family compiler")
        row, cs = compiled

        row["controller_ofs"] = begin
        row["controller_count"] = len(cs)
        rows.append(row)
        controllers.extend(cs)

    return rows, controllers, deferred

