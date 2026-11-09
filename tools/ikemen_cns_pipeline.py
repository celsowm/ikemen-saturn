"""CNS conversion pipeline: parse sources, lower states, and emit assets."""
from __future__ import annotations

import json
from pathlib import Path

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
    *,
    services: dict,
) -> dict:
    Path = services["Path"]
    Section = services["Section"]
    _ExprParser = services["_ExprParser"]
    _split_top_level = services["_split_top_level"]
    collect_states = services["collect_states"]
    parse_sections = services["parse_sections"]
    constants = services["constants"]
    CHARACTER_NAME_HASH = services["CHARACTER_NAME_HASH"]
    LOCALCOORD_X = services["LOCALCOORD_X"]
    Q8 = services["Q8"]
    number = services["number"]
    parse_state = services["parse_state"]
    compile_common_states = services["compile_common_states"]
    STATE_TYPE = services["STATE_TYPE"]
    MOVE_TYPE = services["MOVE_TYPE"]
    PHYSICS = services["PHYSICS"]
    emit_cns_source_files = services["emit_cns_source_files"]

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
    CONST_VALUES = services["CONST_VALUES"]
    CONST_VALUES.clear()
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
            if (section_name == "size" and
                    key.casefold() in {"head.pos", "mid.pos"}):
                # Const(Size.Head.Pos.X/Y) and Const(Size.Mid.Pos.X/Y)
                # are named components in CNS even though [Size] stores
                # each pair under a single key.
                CONST_VALUES[f"{prefix}.x"] = values[0]
                if len(values) > 1:
                    CONST_VALUES[f"{prefix}.y"] = values[1]
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
            if (section_name == "movement" and
                    key.casefold() == "down.bounce.offset"):
                CONST_VALUES[f"{prefix}.x"] = values[0]
                if len(values) > 1:
                    CONST_VALUES[f"{prefix}.y"] = values[1]
    coordinate_scale = 320.0 / LOCALCOORD_X
    CONST_VALUES.setdefault(
        "movement.stand.friction.threshold",
        const["stand_friction_threshold_q8"] / Q8 * coordinate_scale)
    CONST_VALUES.setdefault(
        "movement.crouch.friction.threshold",
        const["crouch_friction_threshold_q8"] / Q8 * coordinate_scale)
    CONST_VALUES.setdefault(
        "movement.down.friction.threshold",
        const["down_friction_threshold_q8"] / Q8 * coordinate_scale)

    # Runtime expressions may reference a character constant that is omitted
    # from its [Velocity] block. Resolve those names using the same defaults
    # used to emit ik_cns_constants_t, so Const(...) and the data table agree.
    velocity_constant_fields = {
        "walk.fwd.x": "walk_fwd_q8",
        "walk.back.x": "walk_back_q8",
        "run.fwd.x": "run_fwd_x_q8",
        "run.fwd.y": "run_fwd_y_q8",
        "run.back.x": "run_back_x_q8",
        "run.back.y": "run_back_y_q8",
        "jump.neu.x": "jump_neu_x_q8",
        "jump.neu.y": "jump_neu_y_q8",
        "jump.back.x": "jump_back_q8",
        "jump.fwd.x": "jump_fwd_q8",
        "runjump.fwd.x": "run_jump_fwd_x_q8",
        "runjump.fwd.y": "run_jump_fwd_y_q8",
        "airjump.neu.x": "air_jump_neu_x_q8",
        "airjump.neu.y": "air_jump_neu_y_q8",
        "airjump.y": "air_jump_neu_y_q8",
        "airjump.back.x": "air_jump_back_q8",
        "airjump.fwd.x": "air_jump_fwd_q8",
        "air.gethit.groundrecover.x": "air_gethit_groundrecover_x_q8",
        "air.gethit.groundrecover.y": "air_gethit_groundrecover_y_q8",
        "air.gethit.airrecover.mul.x": "air_gethit_airrecover_mul_x_q8",
        "air.gethit.airrecover.mul.y": "air_gethit_airrecover_mul_y_q8",
        "air.gethit.airrecover.add.x": "air_gethit_airrecover_add_x_q8",
        "air.gethit.airrecover.add.y": "air_gethit_airrecover_add_y_q8",
        "air.gethit.airrecover.back": "air_gethit_airrecover_back_q8",
        "air.gethit.airrecover.fwd": "air_gethit_airrecover_fwd_q8",
        "air.gethit.airrecover.up": "air_gethit_airrecover_up_q8",
        "air.gethit.airrecover.down": "air_gethit_airrecover_down_q8",
        "air.gethit.ko.add.x": "air_gethit_ko_add_x_q8",
        "air.gethit.ko.add.y": "air_gethit_ko_add_y_q8",
        "air.gethit.ko.ymin": "air_gethit_ko_ymin_q8",
        "ground.gethit.ko.add.x": "ground_gethit_ko_add_x_q8",
        "ground.gethit.ko.add.y": "ground_gethit_ko_add_y_q8",
    }
    for name, field in velocity_constant_fields.items():
        CONST_VALUES.setdefault(
            f"velocity.{name}",
            const[field] / Q8 * coordinate_scale,
        )
    CONST_VALUES.setdefault(
        "movement.air.gethit.groundlevel",
        const["air_gethit_groundlevel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.air.gethit.trip.groundlevel",
        const["air_gethit_trip_groundlevel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.air.gethit.groundrecover.ground.threshold",
        const["air_gethit_groundrecover_threshold_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.air.gethit.groundrecover.groundlevel",
        const["air_gethit_groundrecover_groundlevel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.air.gethit.airrecover.threshold",
        const["air_gethit_airrecover_threshold_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.air.gethit.airrecover.yaccel",
        const["air_gethit_airrecover_yaccel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.down.bounce.yaccel",
        const["down_bounce_yaccel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.down.bounce.groundlevel",
        const["down_bounce_groundlevel_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.down.bounce.offset.x",
        const["down_bounce_offset_x_q8"] / Q8)
    CONST_VALUES.setdefault(
        "movement.down.bounce.offset.y",
        const["down_bounce_offset_y_q8"] / Q8)
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

