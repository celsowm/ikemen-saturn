"""C source and header emission for compiled CNS assets."""
from __future__ import annotations

import re
from pathlib import Path


def emit_cns_source_files(
    out_prefix: Path,
    symbol: str,
    const: dict,
    state_rows: list[dict],
    hitdefs: list[dict],
    sounds: list[dict],
    controllers: list[dict],
    helpers: list[dict],
    explods: list[dict],
    projectiles: list[dict],
    projectile_mods: list[dict],
    reversals: list[dict],
    hitoverrides: list[dict],
) -> None:
    ident = re.sub(r"[^A-Za-z0-9_]", "_", symbol)
    macro = ident.upper()

    expressions: list[dict] = []
    expression_offsets: dict[tuple, tuple[int, int]] = {}

    def intern_expression(code: list[dict] | None) -> tuple[int, int]:
        if not code:
            return 0, 0
        key = tuple(tuple(sorted(ins.items())) for ins in code)
        existing = expression_offsets.get(key)
        if existing is not None:
            return existing
        result = (len(expressions), len(code))
        expression_offsets[key] = result
        expressions.extend(code)
        return result

    for row in state_rows:
        (row["power_add_expr_ofs"],
         row["power_add_expr_count"]) = intern_expression(
            row.get("power_add_expr"))
        (row["juggle_expr_ofs"],
         row["juggle_expr_count"]) = intern_expression(
            row.get("juggle_expr"))
        (row["anim_expr_ofs"], row["anim_expr_count"]) = intern_expression(
            row.get("anim_expr"))
        for axis in ("x", "y"):
            key = f"velset_{axis}"
            (row[f"{key}_expr_ofs"], row[f"{key}_expr_count"]) = \
                intern_expression(row.get(f"{key}_expr"))
        (row["hitcount_persist_expr_ofs"],
         row["hitcount_persist_expr_count"]) = intern_expression(
             row.get("hitcount_persist_expr"))
        (row["spr_priority_expr_ofs"], row["spr_priority_expr_count"]) = \
            intern_expression(row.get("spr_priority_expr"))
    hit_power_expr_keys = (
        ("get", "hit"), ("get", "guard"),
        ("give", "hit"), ("give", "guard"),
    )
    for hit in hitdefs:
        (hit["trigger_expr_ofs"], hit["trigger_expr_count"]) = \
            intern_expression(hit.pop("_trigger_expr", None))
        (hit["trigger2_expr_ofs"], hit["trigger2_expr_count"]) = \
            intern_expression(hit.pop("_trigger2_expr", None))
        (hit["air_juggle_expr_ofs"], hit["air_juggle_expr_count"]) = \
            intern_expression(hit.pop("_air_juggle_expr", None))
        for field in (
            "chain_id", "no_chain_id", "no_chain_id2",
            "p1_spr_priority",
        ):
            (hit[f"{field}_expr_ofs"], hit[f"{field}_expr_count"]) = \
                intern_expression(hit.pop(f"_{field}_expr", None))
        for prefix in ("ground_velocity", "air_velocity"):
            for axis in ("x", "y"):
                key = f"{prefix}_{axis}"
                (hit[f"{key}_expr_ofs"], hit[f"{key}_expr_count"]) = \
                    intern_expression(hit.pop(f"_{key}_expr", None))
        for field in (
            "damage", "guard_damage", "pause_p1", "pause_p2",
            "guard_pause_p1", "guard_pause_p2",
            "p2_get_p1_state",
            "mindist_x", "mindist_y", "maxdist_x", "maxdist_y",
            "ground_slide_time", "ground_hit_time", "air_hit_time",
            "guard_hit_time", "guard_slide_time", "guard_ctrl_time",
            "spark_x", "spark_y", "trigger2_spark_y",
            "hit_sound_group", "hit_sound_item",
            "guard_sound_group", "guard_sound_item",
            "fall_recover", "fall_recover_time",
            "spark_no", "guard_spark_no",
            "fall_x_velocity", "fall_y_velocity",
            "fall", "air_fall", "ground_cornerpush_veloff",
            "fall_damage", "envshake_time", "envshake_ampl",
            "envshake_freq", "fall_envshake_time",
            "fall_envshake_ampl", "fall_envshake_freq",
            "guard_velocity_x", "p1_state_no", "p2_state_no",
            "p1_facing", "p2_facing", "yaccel",
        ):
            key = f"{field}_expr"
            hit[f"{key}_ofs"], hit[f"{key}_count"] = intern_expression(
                hit.pop(f"_{key}", None))
        for prefix, suffix in hit_power_expr_keys:
            code_key = f"_{prefix}_power_{suffix}_expr"
            offset_key = f"{prefix}_power_{suffix}_expr_ofs"
            count_key = f"{prefix}_power_{suffix}_expr_count"
            hit[offset_key], hit[count_key] = intern_expression(
                hit.pop(code_key, None))
    for sound in sounds:
        (sound["group_expr_ofs"], sound["group_expr_count"]) = \
            intern_expression(sound.pop("_group_expr", None))
        (sound["item_expr_ofs"], sound["item_expr_count"]) = \
            intern_expression(sound.pop("_item_expr", None))
        (sound["trigger_expr_ofs"], sound["trigger_expr_count"]) = \
            intern_expression(sound.pop("_trigger_expr", None))
    for explod in explods:
        (explod["anim_expr_ofs"], explod["anim_expr_count"]) = \
            intern_expression(explod.pop("_anim_expr", None))
        (explod["facing_expr_ofs"], explod["facing_expr_count"]) = \
            intern_expression(explod.pop("_facing_expr", None))
        (explod["spr_priority_expr_ofs"],
         explod["spr_priority_expr_count"]) = intern_expression(
             explod.pop("_spr_priority_expr", None))
        (explod["bind_time_expr_ofs"], explod["bind_time_expr_count"]) = \
            intern_expression(explod.pop("_bind_time_expr", None))
        (explod["scale_x_expr_ofs"], explod["scale_x_expr_count"]) = \
            intern_expression(explod.pop("_scale_x_expr", None))
        (explod["scale_y_expr_ofs"], explod["scale_y_expr_count"]) = \
            intern_expression(explod.pop("_scale_y_expr", None))
        (explod["alpha_expr_ofs"], explod["alpha_expr_count"]) = \
            intern_expression(explod.pop("_alpha_expr", None))
    for projectile in projectiles:
        (projectile["anim_expr_ofs"], projectile["anim_expr_count"]) = \
            intern_expression(projectile.pop("anim_expr", None))
    for controller in controllers:
        (controller["trigger_expr_ofs"],
         controller["trigger_expr_count"]) = intern_expression(
            controller.pop("trigger_expr", None))
        for value_index in (0, 1):
            ofs_key = f"value{value_index}_expr_ofs"
            count_key = f"value{value_index}_expr_count"
            (controller[ofs_key], controller[count_key]) = intern_expression(
                controller.pop(f"value{value_index}_expr", None))
    if len(expressions) > 65535:
        raise ValueError("CNS expression table exceeds the 16-bit offset limit")

    expression_lines = [
        "    {"
        f"{ins['op']}, {ins.get('field', '0u')}, "
        f"{ins.get('redirect', 'IK_EXPR_REDIRECT_SELF')}, "
        f"{ins.get('redirect_index', 0)}u, "
        f"{ins.get('value0', 0)}, {ins.get('value1', 0)}"
        "},"
        for ins in expressions
    ]

    state_lines = [
        "    {"
        f"{r['number']}, {r['anim']}, {r['power_add']}, "
        f"{r['velset_x_q8']}, {r['velset_y_q8']}, "
        f"{r['state_type']}, {r['move_type']}, {r['physics']}, "
        f"{r['ctrl']}, {r['spr_priority']}, {r['has_velset']}u, "
        f"{r['hitdef_ofs']}u, {r['hitdef_count']}u, "
        f"{r['playsnd_ofs']}u, {r['playsnd_count']}u, "
        f"{r['controller_ofs']}u, {r['controller_count']}u, "
        f"{r.get('land_state', 0)}, "
        f"{r.get('air_accel_q8', 0)}, {r.get('land_level_q8', 0)}, "
        f"{r.get('air_motion_start', 0)}u, "
        f"{r.get('land_ctrl', 0)}u, "
        f"{r.get('juggle', 0)}, {r.get('has_juggle', 0)}u, "
        f"{r.get('owns_air_accel', 0)}u, "
        f"{r.get('hitdef_persist', 0)}u, "
        f"{r.get('reversal_ofs', 0)}u, "
        f"{r.get('reversal_count', 0)}u, "
        f"{r.get('hitoverride_ofs', 0)}u, "
        f"{r.get('hitoverride_count', 0)}u, "
        f"{r.get('assert_special_flags', '0u')}, "
        f"{r.get('land_before_move', 0)}u, "
        f"{r.get('air_accel_q16', 0)}, "
        f"{r.get('power_add_expr_ofs', 0)}u, "
        f"{r.get('power_add_expr_count', 0)}u, "
        f"{r.get('juggle_expr_ofs', 0)}u, "
        f"{r.get('juggle_expr_count', 0)}u, "
        f"{r.get('anim_expr_ofs', 0)}u, "
        f"{r.get('anim_expr_count', 0)}u, "
        f"{r.get('velset_x_expr_ofs', 0)}u, "
        f"{r.get('velset_x_expr_count', 0)}u, "
        f"{r.get('velset_y_expr_ofs', 0)}u, "
        f"{r.get('velset_y_expr_count', 0)}u"
        f", {r.get('hitcount_persist', 0)}u, "
        f"{r.get('hitcount_persist_expr_ofs', 0)}u, "
        f"{r.get('hitcount_persist_expr_count', 0)}u, "
        f"{r.get('spr_priority_expr_ofs', 0)}u, "
        f"{r.get('spr_priority_expr_count', 0)}u"
        "},"
        for r in state_rows
    ]

    hit_lines = [
        "    {"
        f"{h['state_number']}, {h['trigger_kind']}, {h['trigger_value']}, "
        f"{h['damage']}, {h['guard_damage']}, {h['priority']}u, "
        f"{h['pause_p1']}u, {h['pause_p2']}u, "
        f"{h['ground_type']}, {h['ground_slide_time']}u, "
        f"{h['ground_hit_time']}u, {h['air_hit_time']}u, "
        f"{h['ground_velocity_x_q8']}, {h['ground_velocity_y_q8']}, "
        f"{h['air_velocity_x_q8']}, {h['air_velocity_y_q8']}, "
        f"{h['spark_no']}, {h['spark_x']}, {h['spark_y']}, "
        f"{h['hit_sound_group']}, {h['hit_sound_item']}, "
        f"{h['guard_sound_group']}, {h['guard_sound_item']}, "
        f"{h['flags']}, "
        f"{h['guard_flags']}, {h['guard_kill']}u, "
        f"{h['guard_slide_time']}u, "
        f"{h['guard_hit_time']}u, {h['guard_ctrl_time']}u, "
        f"{h['guard_velocity_x_q8']}, "
        f"{h['air_guard_velocity_x_q8']}, "
        f"{h['air_guard_velocity_y_q8']}, "
        f"{h['anim_type']}u, {h['air_anim_type']}u, "
        f"{h['fall_x_velocity_q8']}, {h['fall_y_velocity_q8']}, "
        f"{h['fall_x_velocity_set']}u, {h['fall_recover']}u, "
        f"{h['fall_recover_time']}u, "
        f"{h['down_hit_time']}u, "
        f"{h['down_velocity_x_q8']}, {h['down_velocity_y_q8']}, "
        f"{h['down_bounce']}u, {h['hit_flags']}, "
        f"{h['priority_type']}, {h['air_juggle']}u, "
        f"{h['p1_state_no']}, {h['p2_state_no']}, {h['guard_dist']}, "
        f"{h['p1_facing']}, {h['p2_facing']}, {h['p1_spr_priority']}, "
        f"{h['p2_body_dist_op']}, {h['p2_body_dist_x']}, "
        f"{h['alt_damage']}, {h['alt_damage_prev_state']}, "
        f"{h['trigger2_kind']}, {h['trigger2_value']}, "
        f"{h['yaccel_q8']}, {h['has_trigger2']}u, "
        f"{h['has_alt_damage']}u, "
        f"{h['ground_cornerpush_veloff_q8']}, "
        f"{h['trigger2_spark_y']}, "
        f"{h['guard_spark_no']}, "
        f"{h.get('attack_attr_mask', '0u')}, "
        f"{h.get('fall_damage', 0)}, "
        f"{h.get('envshake_time', 0)}u, "
        f"{h.get('envshake_ampl', 0)}, "
        f"{h.get('envshake_freq', 60)}u, "
        f"{h.get('fall_envshake_time', 0)}u, "
        f"{h.get('fall_envshake_ampl', 0)}, "
        f"{h.get('fall_envshake_freq', 60)}u, "
        f"{h.get('id', 0)}, "
        f"{h.get('chain_id', -1)}, "
        f"{h.get('no_chain_id', -1)}, "
        f"{h.get('no_chain_id2', -1)}, "
        f"{h['fall_anim_type']}u, "
        f"{h['yaccel_q16']}, "
        f"{h.get('get_power_hit', 0)}, {h.get('get_power_guard', 0)}, "
        f"{h.get('give_power_hit', 0)}, {h.get('give_power_guard', 0)}, "
        f"{h.get('power_flags', 0)}u, "
        f"{h.get('mindist_x_q8', 0)}, {h.get('mindist_y_q8', 0)}, "
        f"{h.get('maxdist_x_q8', 0)}, {h.get('maxdist_y_q8', 0)}, "
        f"{h.get('dist_flags', 0)}u, "
        f"{h.get('mindist_x_expr_ofs', 0)}u, "
        f"{h.get('mindist_y_expr_ofs', 0)}u, "
        f"{h.get('maxdist_x_expr_ofs', 0)}u, "
        f"{h.get('maxdist_y_expr_ofs', 0)}u, "
        f"{h.get('mindist_x_expr_count', 0)}u, "
        f"{h.get('mindist_y_expr_count', 0)}u, "
        f"{h.get('maxdist_x_expr_count', 0)}u, "
        f"{h.get('maxdist_y_expr_count', 0)}u, "
        f"{h.get('get_power_hit_expr_ofs', 0)}u, "
        f"{h.get('get_power_guard_expr_ofs', 0)}u, "
        f"{h.get('give_power_hit_expr_ofs', 0)}u, "
        f"{h.get('give_power_guard_expr_ofs', 0)}u, "
        f"{h.get('get_power_hit_expr_count', 0)}u, "
        f"{h.get('get_power_guard_expr_count', 0)}u, "
        f"{h.get('give_power_hit_expr_count', 0)}u, "
        f"{h.get('give_power_guard_expr_count', 0)}u, "
        f"{h.get('trigger_expr_ofs', 0)}u, "
        f"{h.get('trigger_expr_count', 0)}u, "
        f"{h.get('trigger2_expr_ofs', 0)}u, "
        f"{h.get('trigger2_expr_count', 0)}u, "
        f"{h.get('air_juggle_expr_ofs', 0)}u, "
        f"{h.get('air_juggle_expr_count', 0)}u, "
        f"{h.get('ground_velocity_x_expr_ofs', 0)}u, "
        f"{h.get('ground_velocity_x_expr_count', 0)}u, "
        f"{h.get('ground_velocity_y_expr_ofs', 0)}u, "
        f"{h.get('ground_velocity_y_expr_count', 0)}u, "
        f"{h.get('air_velocity_x_expr_ofs', 0)}u, "
        f"{h.get('air_velocity_x_expr_count', 0)}u, "
        f"{h.get('air_velocity_y_expr_ofs', 0)}u, "
        f"{h.get('air_velocity_y_expr_count', 0)}u, "
        f"{h.get('ground_slide_time_expr_ofs', 0)}u, "
        f"{h.get('ground_slide_time_expr_count', 0)}u, "
        f"{h.get('ground_hit_time_expr_ofs', 0)}u, "
        f"{h.get('ground_hit_time_expr_count', 0)}u, "
        f"{h.get('air_hit_time_expr_ofs', 0)}u, "
        f"{h.get('air_hit_time_expr_count', 0)}u, "
        f"{h.get('guard_hit_time_expr_ofs', 0)}u, "
        f"{h.get('guard_hit_time_expr_count', 0)}u, "
        f"{h.get('guard_slide_time_expr_ofs', 0)}u, "
        f"{h.get('guard_slide_time_expr_count', 0)}u, "
        f"{h.get('guard_ctrl_time_expr_ofs', 0)}u, "
        f"{h.get('guard_ctrl_time_expr_count', 0)}u, "
        f"{h.get('damage_expr_ofs', 0)}u, "
        f"{h.get('damage_expr_count', 0)}u, "
        f"{h.get('guard_damage_expr_ofs', 0)}u, "
        f"{h.get('guard_damage_expr_count', 0)}u, "
        f"{h.get('pause_p1_expr_ofs', 0)}u, "
        f"{h.get('pause_p1_expr_count', 0)}u, "
        f"{h.get('pause_p2_expr_ofs', 0)}u, "
        f"{h.get('pause_p2_expr_count', 0)}u, "
        f"{h.get('spark_x_expr_ofs', 0)}u, "
        f"{h.get('spark_x_expr_count', 0)}u, "
        f"{h.get('spark_y_expr_ofs', 0)}u, "
        f"{h.get('spark_y_expr_count', 0)}u, "
        f"{h.get('trigger2_spark_y_expr_ofs', 0)}u, "
        f"{h.get('trigger2_spark_y_expr_count', 0)}u, "
        f"{h.get('hit_sound_group_expr_ofs', 0)}u, "
        f"{h.get('hit_sound_group_expr_count', 0)}u, "
        f"{h.get('hit_sound_item_expr_ofs', 0)}u, "
        f"{h.get('hit_sound_item_expr_count', 0)}u, "
        f"{h.get('guard_sound_group_expr_ofs', 0)}u, "
        f"{h.get('guard_sound_group_expr_count', 0)}u, "
        f"{h.get('guard_sound_item_expr_ofs', 0)}u, "
        f"{h.get('guard_sound_item_expr_count', 0)}u, "
        f"{h.get('fall_recover_expr_ofs', 0)}u, "
        f"{h.get('fall_recover_expr_count', 0)}u, "
        f"{h.get('fall_recover_time_expr_ofs', 0)}u, "
        f"{h.get('fall_recover_time_expr_count', 0)}u, "
        f"{h.get('spark_no_expr_ofs', 0)}u, "
        f"{h.get('spark_no_expr_count', 0)}u, "
        f"{h.get('guard_spark_no_expr_ofs', 0)}u, "
        f"{h.get('guard_spark_no_expr_count', 0)}u, "
        f"{h.get('fall_x_velocity_expr_ofs', 0)}u, "
        f"{h.get('fall_x_velocity_expr_count', 0)}u, "
        f"{h.get('fall_y_velocity_expr_ofs', 0)}u, "
        f"{h.get('fall_y_velocity_expr_count', 0)}u, "
        f"{h.get('fall_expr_ofs', 0)}u, "
        f"{h.get('fall_expr_count', 0)}u, "
        f"{h.get('air_fall_expr_ofs', 0)}u, "
        f"{h.get('air_fall_expr_count', 0)}u, "
        f"{h.get('ground_cornerpush_veloff_expr_ofs', 0)}u, "
        f"{h.get('ground_cornerpush_veloff_expr_count', 0)}u, "
        f"{h.get('fall_damage_expr_ofs', 0)}u, "
        f"{h.get('fall_damage_expr_count', 0)}u, "
        f"{h.get('envshake_time_expr_ofs', 0)}u, "
        f"{h.get('envshake_time_expr_count', 0)}u, "
        f"{h.get('envshake_ampl_expr_ofs', 0)}u, "
        f"{h.get('envshake_ampl_expr_count', 0)}u, "
        f"{h.get('envshake_freq_expr_ofs', 0)}u, "
        f"{h.get('envshake_freq_expr_count', 0)}u, "
        f"{h.get('fall_envshake_time_expr_ofs', 0)}u, "
        f"{h.get('fall_envshake_time_expr_count', 0)}u, "
        f"{h.get('fall_envshake_ampl_expr_ofs', 0)}u, "
        f"{h.get('fall_envshake_ampl_expr_count', 0)}u, "
        f"{h.get('fall_envshake_freq_expr_ofs', 0)}u, "
        f"{h.get('fall_envshake_freq_expr_count', 0)}u, "
        f"{h.get('guard_velocity_x_expr_ofs', 0)}u, "
        f"{h.get('guard_velocity_x_expr_count', 0)}u, "
        f"{h.get('p1_state_no_expr_ofs', 0)}u, "
        f"{h.get('p1_state_no_expr_count', 0)}u, "
        f"{h.get('p2_state_no_expr_ofs', 0)}u, "
        f"{h.get('p2_state_no_expr_count', 0)}u, "
        f"{h.get('p1_facing_expr_ofs', 0)}u, "
        f"{h.get('p1_facing_expr_count', 0)}u, "
        f"{h.get('p2_facing_expr_ofs', 0)}u, "
        f"{h.get('p2_facing_expr_count', 0)}u, "
        f"{h.get('yaccel_expr_ofs', 0)}u, "
        f"{h.get('yaccel_expr_count', 0)}u, "
        f"{h.get('attack_state_mask', 0)}u, "
        f"{h.get('chain_id_expr_ofs', 0)}u, "
        f"{h.get('chain_id_expr_count', 0)}u, "
        f"{h.get('no_chain_id_expr_ofs', 0)}u, "
        f"{h.get('no_chain_id_expr_count', 0)}u, "
        f"{h.get('no_chain_id2_expr_ofs', 0)}u, "
        f"{h.get('no_chain_id2_expr_count', 0)}u, "
        f"{h.get('p1_spr_priority_expr_ofs', 0)}u, "
        f"{h.get('p1_spr_priority_expr_count', 0)}u, "
        f"{h.get('air_type', 'IK_CNS_GROUND_NORMAL')}, "
        f"{h.get('guard_pause_p1', h.get('pause_p1', 0))}u, "
        f"{h.get('guard_pause_p2', h.get('pause_p2', 0))}u, "
        f"{h.get('guard_pause_p1_expr_ofs', 0)}u, "
        f"{h.get('guard_pause_p1_expr_count', 0)}u, "
        f"{h.get('guard_pause_p2_expr_ofs', 0)}u, "
        f"{h.get('guard_pause_p2_expr_count', 0)}u, "
        f"{h.get('p2_get_p1_state', 0)}u, "
        f"{h.get('p2_get_p1_state_expr_ofs', 0)}u, "
        f"{h.get('p2_get_p1_state_expr_count', 0)}u"
        "},"
        for h in hitdefs
    ]

    sound_lines = [
        f"    {{{p['state_number']}, {p['trigger_kind']}, "
        f"{p['trigger_value']}, {p['group']}, {p['item']}, "
        f"{p.get('channel', -1)}, "
        f"{p.get('group_expr_ofs', 0)}u, "
        f"{p.get('group_expr_count', 0)}u, "
        f"{p.get('item_expr_ofs', 0)}u, "
        f"{p.get('item_expr_count', 0)}u, "
        f"{p.get('trigger_expr_ofs', 0)}u, "
        f"{p.get('trigger_expr_count', 0)}u}},"
        for p in sounds
    ]

    controller_lines = [
        f"    {{{c['state_number']}, {c['type']}, {c['trigger_kind']}, "
        f"{c['trigger_value']}, {c['trigger_value2']}, "
        f"{c['value0']}, {c['value1']}, {c['flags']}, "
        f"{c.get('value2', 0)}, {c.get('value3', 0)}, "
        f"{c.get('value4', 0)}, {c.get('value5', 0)}, "
        f"{c.get('value6', 0)}, {c.get('value7', 0)}, "
        f"{c.get('trigger_aux', -1)}, "
        f"{c.get('trigger_expr_ofs', 0)}u, "
        f"{c.get('trigger_expr_count', 0)}u, "
        f"{c.get('value0_expr_ofs', 0)}u, "
        f"{c.get('value0_expr_count', 0)}u, "
        f"{c.get('value1_expr_ofs', 0)}u, "
        f"{c.get('value1_expr_count', 0)}u}},"
        for c in controllers
    ]

    explod_lines = [
        "    {"
        f"{e['anim_no']}, {e['pos_x_q8']}, {e['pos_y_q8']}, "
        f"{e['vel_x_q8']}, {e['vel_y_q8']}, "
        f"{e['accel_x_q8']}, {e['accel_y_q8']}, "
        f"{e['remove_time']}, {e['spr_priority']}, {e['postype']}, "
        f"{e.get('ownpal', 0)}u, {e.get('pause_move_time', 0)}u, "
        f"{e.get('super_move_time', 0)}u, "
        f"{e.get('bind_time', 0)}, "
        f"{e.get('remove_on_gethit', 0)}u, "
        f"{e.get('remove_on_state_change', 0)}u, "
        f"{e.get('facing', 1)}, {e.get('vfacing', 1)}, "
        f"{e.get('scale_x_q8', 256)}, {e.get('scale_y_q8', 256)}, "
        f"{e.get('trans_mode', 'IK_CNS_TRANS_NONE')}, "
        f"{e.get('alpha', 255)}u, {e.get('id', -1)}, "
        f"{e.get('under', 0)}u, {e.get('ontop', 0)}u, "
        f"{e.get('random_x_q8', 0)}, {e.get('random_y_q8', 0)}, "
        f"{e.get('has_shadow', 0)}u, {e.get('use_fightfx', 0)}u, "
        f"{e.get('anim_expr_ofs', 0)}u, "
        f"{e.get('anim_expr_count', 0)}u, "
        f"{e.get('facing_expr_ofs', 0)}u, "
        f"{e.get('facing_expr_count', 0)}u, "
        f"{e.get('spr_priority_expr_ofs', 0)}u, "
        f"{e.get('spr_priority_expr_count', 0)}u, "
        f"{e.get('bind_time_expr_ofs', 0)}u, "
        f"{e.get('bind_time_expr_count', 0)}u, "
        f"{e.get('scale_x_expr_ofs', 0)}u, "
        f"{e.get('scale_x_expr_count', 0)}u, "
        f"{e.get('scale_y_expr_ofs', 0)}u, "
        f"{e.get('scale_y_expr_count', 0)}u, "
        f"{e.get('alpha_expr_ofs', 0)}u, "
        f"{e.get('alpha_expr_count', 0)}u"
        "},"
        for e in explods
    ]

    projectile_lines = [
        "    {"
        f"{p['id']}, {p['anim_no']}, {p['hit_anim_no']}, "
        f"{p['remove_anim_no']}, {p['cancel_anim_no']}, "
        f"{p['hitdef_global']}, "
        f"{p['pos_x_q8']}, {p['pos_y_q8']}, "
        f"{p['vel_x_q8']}, {p['vel_y_q8']}, "
        f"{p['velmul_x_q8']}, {p['velmul_y_q8']}, "
        f"{p['accel_x_q8']}, {p['accel_y_q8']}, "
        f"{p['remove_time']}, {p['edge_bound']}, {p['stage_bound']}, "
        f"{p['hits']}u, {p['miss_time']}u, {p['priority']}u, "
        f"{p['remove_on_hit']}u, {p['spr_priority']}, "
        f"{p['ownpal']}u, {p['pause_move_time']}u, "
        f"{p['super_move_time']}u, "
        f"{p.get('bind_time', 0)}, "
        f"{p.get('remove_on_gethit', 0)}u, "
        f"{p.get('remove_on_state_change', 0)}u, "
        f"{p.get('postype', 'IK_CNS_HELPER_POS_P1')}, "
        f"{p.get('has_shadow', 0)}u, "
        f"{p.get('shadow_r', 0)}u, {p.get('shadow_g', 0)}u, "
        f"{p.get('shadow_b', 0)}u, "
        f"{p.get('anim_expr_ofs', 0)}u, "
        f"{p.get('anim_expr_count', 0)}u, "
        f"{p.get('height_bound_low', -240)}, "
        f"{p.get('height_bound_high', 1)}, "
        f"{p.get('height_bound_set', 0)}u"
        "},"
        for p in projectiles
    ]

    projectile_mod_lines = [
        "    {"
        f"{m['id']}, {m.get('index', 0)}, {m['mask']}, "
        f"{m['anim_no']}, {m['hit_anim_no']}, "
        f"{m['remove_anim_no']}, {m['cancel_anim_no']}, "
        f"{m['vel_x_q8']}, {m['vel_y_q8']}, "
        f"{m['velmul_x_q8']}, {m['velmul_y_q8']}, "
        f"{m['accel_x_q8']}, {m['accel_y_q8']}, "
        f"{m['remove_time']}, {m['edge_bound']}, {m['stage_bound']}, "
        f"{m['hits']}u, {m['miss_time']}u, {m['priority']}u, "
        f"{m['remove_on_hit']}u, {m['spr_priority']}, "
        f"{m['pause_move_time']}u, {m['super_move_time']}u, "
        f"{m['bind_time']}, {m['remove_on_gethit']}u, "
        f"{m['remove_on_state_change']}u"
        "},"
        for m in projectile_mods
    ]

    reversal_lines = [
        "    {"
        f"{r['state_number']}, {r['start_time']}u, {r['end_time']}u, "
        f"{r['attacker_state_mask']}, "
        f"{r.get('incoming_attr_mask', '0u')}, "
        f"{r['pause_p1']}u, {r['pause_p2']}u, "
        f"{r['spark_no']}, {r['spark_x']}, {r['spark_y']}, "
        f"{r['hit_sound_group']}, {r['hit_sound_item']}, "
        f"{r['p1_state_no']}, "
        f"{r['p1_spr_priority']}, {r['p2_spr_priority']}"
        "},"
        for r in reversals
    ]

    hitoverride_lines = [
        "    {"
        f"{h['state_number']}, {h['start_time']}u, {h['end_time']}u, "
        f"{h['self_state_mask']}, {h['incoming_attr_mask']}, "
        f"{h['target_state']}"
        "},"
        for h in hitoverrides
    ]

    helper_lines = [
        "    {"
        f"{h['id']}, {h['state_no']}, "
        f"{h['pos_x_q8']}, {h['pos_y_q8']}, "
        f"{h['facing']}, {h['postype']}, "
        f"{h['keyctrl']}u, {h['ownpal']}u, "
        f"{h.get('pause_move_time', 0)}u, "
        f"{h.get('super_move_time', 0)}u, "
        f"{h.get('name_hash', 0)}u, {h.get('spr_priority', 0)}"
        "},"
        for h in helpers
    ]

    constant_fields = (
        "life", "ground_back", "ground_front", "air_back", "air_front",
        "height", "attack_dist", "head_pos_x", "head_pos_y", "mid_pos_x",
        "mid_pos_y", "walk_fwd_q8", "walk_back_q8", "run_fwd_x_q8",
        "run_fwd_y_q8", "run_back_x_q8", "run_back_y_q8", "jump_neu_x_q8",
        "jump_neu_y_q8", "jump_back_q8", "jump_fwd_q8",
        "run_jump_fwd_x_q8", "run_jump_fwd_y_q8", "air_jump_neu_x_q8",
        "air_jump_neu_y_q8", "air_jump_back_q8", "air_jump_fwd_q8",
        "air_jump_num", "air_jump_height", "yaccel_q8", "stand_friction_q8",
        "crouch_friction_q8", "stand_friction_threshold_q8",
        "crouch_friction_threshold_q8", "liedown_time",
        "air_gethit_groundlevel_q8", "air_gethit_trip_groundlevel_q8",
        "down_bounce_offset_x_q8", "down_bounce_offset_y_q8",
        "down_bounce_yaccel_q8", "down_bounce_groundlevel_q8",
        "down_friction_threshold_q8", "air_gethit_groundrecover_x_q8",
        "air_gethit_groundrecover_y_q8",
        "air_gethit_groundrecover_threshold_q8",
        "air_gethit_groundrecover_groundlevel_q8",
        "air_gethit_airrecover_mul_x_q8", "air_gethit_airrecover_mul_y_q8",
        "air_gethit_airrecover_add_x_q8", "air_gethit_airrecover_add_y_q8",
        "air_gethit_airrecover_back_q8", "air_gethit_airrecover_fwd_q8",
        "air_gethit_airrecover_up_q8", "air_gethit_airrecover_down_q8",
        "air_gethit_airrecover_threshold_q8", "air_gethit_airrecover_yaccel_q8",
        "air_juggle", "yaccel_q16", "stand_friction_q16",
        "crouch_friction_q16", "air_gethit_ko_add_x_q8",
        "air_gethit_ko_add_y_q8", "air_gethit_ko_ymin_q8",
        "ground_gethit_ko_xmul_q16", "ground_gethit_ko_add_x_q8",
        "ground_gethit_ko_add_y_q8", "ground_gethit_ko_ymin_q8",
    )
    constants_init = "{ " + ", ".join(
        str(const[field]) for field in constant_fields
    ) + (f", 1u, {const['character_name_hash']}u, "
         f"{const['character_author_hash']}u, "
         f"{const['attack']}, {const['defence']} " + "}")

    generated_c = f"""/* Auto-generated by tools/ikemen_cns.py. */
#include "ikemen_saturn/ikemen_cns.h"
#include "{out_prefix.name}.h"

const ik_cns_constants_t {ident}_cns_constants = {constants_init};

static const ik_cns_state_t {ident}_states[{max(1, len(state_rows))}] = {{
{chr(10).join(state_lines) if state_lines else '    {0},'}
}};

static const ik_expr_instr_t {ident}_expressions[{max(1, len(expressions))}] = {{
{chr(10).join(expression_lines) if expression_lines else '    {0},'}
}};

static const ik_cns_hitdef_t {ident}_hitdefs[{max(1, len(hit_lines))}] = {{
{chr(10).join(hit_lines) if hit_lines else '    {0},'}
}};

static const ik_cns_playsnd_t {ident}_playsnds[{max(1, len(sound_lines))}] = {{
{chr(10).join(sound_lines) if sound_lines else '    {0},'}
}};

static const ik_cns_controller_t {ident}_controllers[{max(1, len(controller_lines))}] = {{
{chr(10).join(controller_lines) if controller_lines else '    {0},'}
}};

static const ik_cns_helper_t {ident}_helpers[{max(1, len(helper_lines))}] = {{
{chr(10).join(helper_lines) if helper_lines else '    {0},'}
}};

static const ik_cns_explod_t {ident}_explods[{max(1, len(explod_lines))}] = {{
{chr(10).join(explod_lines) if explod_lines else '    {0},'}
}};

static const ik_cns_projectile_t {ident}_projectiles[{max(1, len(projectile_lines))}] = {{
{chr(10).join(projectile_lines) if projectile_lines else '    {0},'}
}};

static const ik_cns_projectile_mod_t {ident}_projectile_mods[{max(1, len(projectile_mod_lines))}] = {{
{chr(10).join(projectile_mod_lines) if projectile_mod_lines else '    {0},'}
}};

static const ik_cns_reversaldef_t {ident}_reversals[{max(1, len(reversal_lines))}] = {{
{chr(10).join(reversal_lines) if reversal_lines else '    {0},'}
}};

static const ik_cns_hitoverride_t {ident}_hitoverrides[{max(1, len(hitoverride_lines))}] = {{
{chr(10).join(hitoverride_lines) if hitoverride_lines else '    {0},'}
}};

const ik_cns_asset_t {ident}_cns = {{
    {{
        {const['life']},
        {const['ground_back']}, {const['ground_front']},
        {const['air_back']}, {const['air_front']}, {const['height']},
        {const['attack_dist']},
        {const['head_pos_x']}, {const['head_pos_y']},
        {const['mid_pos_x']}, {const['mid_pos_y']},
        {const['walk_fwd_q8']}, {const['walk_back_q8']},
        {const['run_fwd_x_q8']}, {const['run_fwd_y_q8']},
        {const['run_back_x_q8']}, {const['run_back_y_q8']},
        {const['jump_neu_x_q8']}, {const['jump_neu_y_q8']},
        {const['jump_back_q8']}, {const['jump_fwd_q8']},
        {const['run_jump_fwd_x_q8']}, {const['run_jump_fwd_y_q8']},
        {const['air_jump_neu_x_q8']}, {const['air_jump_neu_y_q8']},
        {const['air_jump_back_q8']}, {const['air_jump_fwd_q8']},
        {const['air_jump_num']}, {const['air_jump_height']},
        {const['yaccel_q8']}, {const['stand_friction_q8']},
        {const['crouch_friction_q8']},
        {const['stand_friction_threshold_q8']},
        {const['crouch_friction_threshold_q8']},
        {const['liedown_time']},
        {const['air_gethit_groundlevel_q8']},
        {const['air_gethit_trip_groundlevel_q8']},
        {const['down_bounce_offset_x_q8']},
        {const['down_bounce_offset_y_q8']},
        {const['down_bounce_yaccel_q8']},
        {const['down_bounce_groundlevel_q8']},
        {const['down_friction_threshold_q8']},
        {const['air_gethit_groundrecover_x_q8']},
        {const['air_gethit_groundrecover_y_q8']},
        {const['air_gethit_groundrecover_threshold_q8']},
        {const['air_gethit_groundrecover_groundlevel_q8']},
        {const['air_gethit_airrecover_mul_x_q8']},
        {const['air_gethit_airrecover_mul_y_q8']},
        {const['air_gethit_airrecover_add_x_q8']},
        {const['air_gethit_airrecover_add_y_q8']},
        {const['air_gethit_airrecover_back_q8']},
        {const['air_gethit_airrecover_fwd_q8']},
        {const['air_gethit_airrecover_up_q8']},
        {const['air_gethit_airrecover_down_q8']},
        {const['air_gethit_airrecover_threshold_q8']},
        {const['air_gethit_airrecover_yaccel_q8']},
        {const['air_juggle']},
        {const['yaccel_q16']}, {const['stand_friction_q16']},
        {const['crouch_friction_q16']},
        {const['air_gethit_ko_add_x_q8']},
        {const['air_gethit_ko_add_y_q8']},
        {const['air_gethit_ko_ymin_q8']},
        {const['ground_gethit_ko_xmul_q16']},
        {const['ground_gethit_ko_add_x_q8']},
        {const['ground_gethit_ko_add_y_q8']},
        {const['ground_gethit_ko_ymin_q8']},
        1u, {const['character_name_hash']}u,
        {const['character_author_hash']}u,
        {const['attack']}, {const['defence']}
    }},
    {ident}_states, {len(state_rows)}u,
    {ident}_hitdefs, {len(hitdefs)}u,
    {ident}_playsnds, {len(sounds)}u,
    {ident}_controllers, {len(controllers)}u,
    {ident}_helpers, {len(helpers)}u,
    {ident}_reversals, {len(reversals)}u,
    {ident}_hitoverrides, {len(hitoverrides)}u,
    {ident}_explods, {len(explods)}u,
    {ident}_projectiles, {len(projectiles)}u,
    {ident}_projectile_mods, {len(projectile_mods)}u,
    {ident}_expressions, {len(expressions)}u
}};
"""

    generated_h = f"""/* Auto-generated by tools/ikemen_cns.py. */
#pragma once

#include "ikemen_saturn/ikemen_cns.h"

#define {macro}_CNS_STATE_COUNT {len(state_rows)}u
#define {macro}_CNS_HITDEF_COUNT {len(hitdefs)}u
#define {macro}_CNS_PLAYSND_COUNT {len(sounds)}u
#define {macro}_CNS_CONTROLLER_COUNT {len(controllers)}u
#define {macro}_CNS_HELPER_COUNT {len(helpers)}u
#define {macro}_CNS_EXPLOD_COUNT {len(explods)}u
#define {macro}_CNS_PROJECTILE_COUNT {len(projectiles)}u
#define {macro}_CNS_PROJECTILE_MOD_COUNT {len(projectile_mods)}u
#define {macro}_CNS_REVERSAL_COUNT {len(reversals)}u
#define {macro}_CNS_HITOVERRIDE_COUNT {len(hitoverrides)}u
#define {macro}_CNS_EXPRESSION_COUNT {len(expressions)}u

extern const ik_cns_asset_t {ident}_cns;
extern const ik_cns_constants_t {ident}_cns_constants;
"""

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    out_prefix.with_suffix(".c").write_text(generated_c, encoding="utf-8")
    out_prefix.with_suffix(".h").write_text(generated_h, encoding="utf-8")

