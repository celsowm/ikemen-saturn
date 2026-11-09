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
import re
from pathlib import Path
try:
    from .ikemen_cns_expr import (
        _ExprParser, character_name_hash,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_expr import (
        _ExprParser, character_name_hash,
    )
try:
    from .ikemen_cns_runtime_values import (
        compile_cns_expr, compile_controller_trigger_expr,
        dist_fields, dynamic_power_add_expr, eval_expr, eval_int,
        integer_or_runtime_expr, number_or_runtime_expr,
        pair_integer_runtime_expr, pair_runtime_expr, power_fields,
        sound_pair, sound_pair_runtime, spark_pair, spark_pair_runtime,
        configure as configure_runtime_values,
    )
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_runtime_values import (
        compile_cns_expr, compile_controller_trigger_expr,
        dist_fields, dynamic_power_add_expr, eval_expr, eval_int,
        integer_or_runtime_expr, number_or_runtime_expr,
        pair_integer_runtime_expr, pair_runtime_expr, power_fields,
        sound_pair, sound_pair_runtime, spark_pair, spark_pair_runtime,
        configure as configure_runtime_values,
    )
try:
    from .ikemen_cns_pipeline import emit as emit_cns_pipeline
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_pipeline import emit as emit_cns_pipeline
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

try:
    from .ikemen_cns_cli import main as cli_main
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_cli import main as cli_main

Q8 = 256
STRICT_CONVERSION = False
COMMAND_IDS: dict[str, int] = {}
LOCALCOORD_X = 320.0
CONST_VALUES: dict[str, float] = {}
CHARACTER_NAME_HASH = 0
SELF_ANIMS: set[int] | None = None
_SELF_ANIM_TERM = re.compile(
    r"(!?)\s*SelfAnimExist\s*\(\s*(\d+)\s*\)", re.I)

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





def simple_trigger(section: Section) -> tuple[str, int, int]:
    return _cns_triggers.compile_simple_trigger(section, services=globals())


def hitdef_trigger(section: Section):
    return _cns_triggers.compile_hitdef_trigger(section, services=globals())


def _strip_outer_parens(text: str) -> str:
    return _cns_triggers.strip_outer_parens(text)


def _anim_elem_range_trigger(expr: str) -> tuple[int, int] | None:
    return _cns_triggers.anim_elem_range_trigger(expr)


def _move_contact_window(triggers: list[str]) -> tuple[int, int] | None:
    return _cns_triggers.move_contact_window(triggers)


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
    return _cns_character.compile_character_constants(
        globals_, services=globals())

try:
    from . import ikemen_cns_character as _cns_character
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    import ikemen_cns_character as _cns_character


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
    return emit_cns_pipeline(
        path, selected, out_prefix, symbol, common_zss, common_selected,
        constants_source, character_zss, hits_zss, states_sources,
        services=globals(),
    )


def main(argv: list[str] | None = None) -> int:
    return cli_main(argv, services={
        **globals(),
        "namespace": __import__(__name__, fromlist=["*"]),
    })


if __name__ == "__main__":
    raise SystemExit(main())
