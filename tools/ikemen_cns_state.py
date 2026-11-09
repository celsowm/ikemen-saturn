"""Statedef and controller conversion for CNS assets."""
from __future__ import annotations

import re
try:
    from .ikemen_cns_parse import Section, State
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section, State


def compile_state(
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
    *,
    services: dict,
):
    GROUND_TYPE = services['GROUND_TYPE']
    MOVE_TYPE = services['MOVE_TYPE']
    PHYSICS = services['PHYSICS']
    STATE_TYPE = services['STATE_TYPE']
    STRICT_CONVERSION = services['STRICT_CONVERSION']
    Section = services['Section']
    _split_top_level = services['_split_top_level']
    _strip_outer_parens = services['_strip_outer_parens']
    anim_type_code = services['anim_type_code']
    attack_attr_mask = services['attack_attr_mask']
    attack_state_mask = services['attack_state_mask']
    compile_cns_expr = services['compile_cns_expr']
    compile_explod_controller = services['compile_explod_controller']
    compile_helper_controller = services['compile_helper_controller']
    compile_modify_projectile_controller = services['compile_modify_projectile_controller']
    compile_projectile_controller = services['compile_projectile_controller']
    compile_runtime_controller = services['compile_runtime_controller']
    compile_controller_trigger_expr = services['compile_controller_trigger_expr']
    controller_requires_runtime_expr = services['controller_requires_runtime_expr']
    dist_fields = services['dist_fields']
    dynamic_power_add_expr = services['dynamic_power_add_expr']
    eval_int = services['eval_int']
    fall_anim_type_code = services['fall_anim_type_code']
    fold_self_anim_exist = services['fold_self_anim_exist']
    guard_mask = services['guard_mask']
    guard_times_runtime = services['guard_times_runtime']
    hit_mask = services['hit_mask']
    hitdef_trigger = services['hitdef_trigger']
    integer = services['integer']
    integer_or_runtime_expr = services['integer_or_runtime_expr']
    no_hit_by_state_mask = services['no_hit_by_state_mask']
    number_or_runtime_expr = services['number_or_runtime_expr']
    pair = services['pair']
    pair_integer_runtime_expr = services['pair_integer_runtime_expr']
    pair_runtime_expr = services['pair_runtime_expr']
    power_fields = services['power_fields']
    priority_type_code = services['priority_type_code']
    q16 = services['q16']
    q8 = services['q8']
    reversal_state_mask = services['reversal_state_mask']
    simple_trigger = services['simple_trigger']
    sound_pair = services['sound_pair']
    sound_pair_runtime = services['sound_pair_runtime']
    spark_pair = services['spark_pair']
    spark_pair_runtime = services['spark_pair_runtime']

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
    unsupported_details: list[dict[str, str]] = []
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

    def attach_runtime_trigger_expression(
        controller: dict,
        section: Section,
    ) -> bool:
        expression = getattr(section, "runtime_trigger_expr", None)
        if expression is None and not controller_requires_runtime_expr(section):
            return True
        try:
            if expression is None:
                expression = compile_controller_trigger_expr(section)
        except ValueError:
            if STRICT_CONVERSION:
                raise
            section.unsupported_reason = "unsupported trigger expression"
            return False
        controller["trigger_expr"] = expression
        controller["trigger_kind"] = "IK_CNS_TRIGGER_ALWAYS"
        controller["trigger_value"] = 0
        controller["trigger_value2"] = 0
        return True

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
            alt_damage_prev_state = -2147483648
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
                integer_or_runtime_expr(
                    ctrl.get("fall.recovertime"), 4,
                )
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
            p1_state_no, p1_state_no_expr = integer_or_runtime_expr(
                ctrl.get("p1stateno"), -1)
            p2_state_no, p2_state_no_expr = integer_or_runtime_expr(
                ctrl.get("p2stateno"), -1)
            p1_facing, p1_facing_expr = integer_or_runtime_expr(
                ctrl.get("p1facing"), 0)
            p2_facing, p2_facing_expr = integer_or_runtime_expr(
                ctrl.get("p2facing"), 0)
            p1_spr_priority, p1_spr_priority_expr = integer_or_runtime_expr(
                ctrl.get("p1sprpriority"), -128)
            no_chain_parts = _split_top_level(
                ctrl.get("nochainid") or "-1,-1")
            no_chain_parts = (no_chain_parts + ["-1", "-1"])[:2]
            yaccel, yaccel_expr = number_or_runtime_expr(
                ctrl.get("yaccel"), .35)

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
                    "_p1_state_no_expr": p1_state_no_expr,
                    "_p2_state_no_expr": p2_state_no_expr,
                    "_p1_facing_expr": p1_facing_expr,
                    "_p2_facing_expr": p2_facing_expr,
                    "_yaccel_expr": yaccel_expr,
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
                    "air_type": GROUND_TYPE.get(
                        (
                            ctrl.get("air.type")
                            or ctrl.get("ground.type", "normal")
                            or "normal"
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
                    "p1_state_no": p1_state_no,
                    "p2_state_no": p2_state_no,
                    "guard_dist": integer(ctrl.get("guard.dist"), -1),
                    "p1_facing": p1_facing,
                    "p2_facing": p2_facing,
                    "p1_spr_priority": p1_spr_priority,
                    "_p1_spr_priority_expr": p1_spr_priority_expr,
                    "p2_body_dist_op": p2_dist_op,
                    "p2_body_dist_x": p2_dist_x,
                    "alt_damage": alt_damage,
                    "alt_damage_prev_state": alt_damage_prev_state,
                    "yaccel_q8": q8(yaccel),
                    "yaccel_q16": q16(yaccel),
                    **power_fields(ctrl),
                    **dist_fields(ctrl),
                    "has_alt_damage": int(damage_expr is not None),
                    "ground_cornerpush_veloff_q8": q8(cornerpush_veloff),
                    "attack_attr_mask": attack_attr_mask(
                        attr_parts[1] if len(attr_parts) > 1 else ""
                    ),
                    "attack_state_mask": attack_state_mask(
                        attr_parts[0] if attr_parts else "SCA"
                    ),
                    "fall_damage": fall_damage,
                    "envshake_time": envshake_time,
                    "envshake_ampl": envshake_ampl,
                    "envshake_freq": envshake_freq,
                    "fall_envshake_time": fall_envshake_time,
                    "fall_envshake_ampl": fall_envshake_ampl,
                    "fall_envshake_freq": fall_envshake_freq,
                    "id": integer(ctrl.get("id"), 0),
                    "chain_id": integer_or_runtime_expr(
                        ctrl.get("chainid"), -1)[0],
                    "_chain_id_expr": integer_or_runtime_expr(
                        ctrl.get("chainid"), -1)[1],
                    "no_chain_id": integer_or_runtime_expr(
                        no_chain_parts[0], -1)[0],
                    "_no_chain_id_expr": integer_or_runtime_expr(
                        no_chain_parts[0], -1)[1],
                    "no_chain_id2": integer_or_runtime_expr(
                        no_chain_parts[1], -1)[0],
                    "_no_chain_id2_expr": integer_or_runtime_expr(
                        no_chain_parts[1], -1)[1],
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
            try:
                duration = integer(ctrl.get("time"), 1)
            except ValueError:
                unsupported.append("hitoverride")
                continue
            duration = 65535 if duration == -1 else max(1, duration)
            m_eq = re.fullmatch(r"Time\s*=\s*(\d+)", expr, flags=re.I)
            m_lt = re.fullmatch(r"Time\s*<\s*(\d+)", expr, flags=re.I)
            if (
                re.fullmatch(r"(?:1(?:\.0+)?|true)", expr, flags=re.I) or
                re.fullmatch(r"Time\s*>=\s*0", expr, flags=re.I)
            ):
                # A continuously true HitOverride re-registers every tick and
                # remains active for the duration of this state.
                start_time = 0
                end_time = 65535
            elif (
                re.fullmatch(r"!?\s*Time\s*=\s*0", expr, flags=re.I) or
                re.fullmatch(r"!\s*Time", expr, flags=re.I)
            ):
                start_time = 0
                end_time = min(65535, duration)
            elif m_eq:
                start_time = int(m_eq.group(1))
                end_time = min(65535, start_time + duration)
            elif m_lt:
                start_time = 0
                end_time = int(m_lt.group(1))
            else:
                unsupported.append("hitoverride")
                continue

            override_state = (ctrl.get("stateno") or "-1").strip()
            target_state = (
                state.number
                if override_state.casefold() == "stateno" else
                integer(override_state, -1)
            )
            hitoverrides.append({
                "state_number": state.number,
                "start_time": start_time,
                "end_time": end_time,
                "self_state_mask": self_mask,
                "incoming_attr_mask": incoming_mask,
                "target_state": target_state,
            })

        elif ctype == "playsnd":
            sound_parts = _split_top_level(ctrl.get("value") or "")
            if len(sound_parts) not in (1, 2):
                raise ValueError(
                    f"expected sound group,item, got {ctrl.get('value')!r}")
            group_text = sound_parts[0].strip()
            if group_text[:1].casefold() in {"s", "f"}:
                group_text = group_text[1:]
            sound_group, group_expr = integer_or_runtime_expr(group_text, 0)
            item_text = sound_parts[1] if len(sound_parts) == 2 else "0"
            item, item_expr = integer_or_runtime_expr(item_text, 0)
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
                        if (trig_kind == "IK_CNS_TRIGGER_ALWAYS" and
                                trigger_exprs[0].strip().casefold() not in
                                {"1", "1.0", "true"}):
                            trigger_expr = compile_cns_expr(
                                trigger_exprs[0], q16=True)
                    else:
                        raise ValueError("combined trigger expression")
                except ValueError:
                    expression_text = " && ".join(trigger_exprs) or "1"
                    try:
                        trigger_expr = compile_cns_expr(
                            expression_text, q16=True)
                    except ValueError:
                        if STRICT_CONVERSION:
                            raise
                        unsupported.append(ctype)
                        continue
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
                try:
                    trigger_expr = (
                        compile_cns_expr(
                            " && ".join(triggerall), q16=True)
                        if triggerall else None
                    )
                except ValueError:
                    if STRICT_CONVERSION:
                        raise
                    unsupported.append(ctype)
                    continue
                sounds.append({
                    "state_number": state.number,
                    "trigger_kind": "IK_CNS_TRIGGER_ALWAYS",
                    "trigger_value": 0,
                    "group": sound_group,
                    "item": item,
                    "_group_expr": group_expr,
                    "_item_expr": item_expr,
                    "_trigger_expr": trigger_expr,
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
                if attach_runtime_trigger_expression(controller, ctrl):
                    controllers.append(
                        attach_target_query_selector(controller, ctrl)
                    )
                    helpers.append(helper)
                else:
                    unsupported.append(ctype)
            else:
                unsupported.append(ctype)

        elif ctype == "explod":
            try:
                compiled_explod = compile_explod_controller(
                    state.number, ctrl, explod_ofs + len(explods)
                )
            except ValueError as exc:
                compiled_explod = None
                ctrl.unsupported_reason = str(exc)
            if compiled_explod is not None:
                controller, explod = compiled_explod
                if attach_runtime_trigger_expression(controller, ctrl):
                    controllers.append(
                        attach_target_query_selector(controller, ctrl)
                    )
                    explods.append(explod)
                else:
                    unsupported.append(ctype)
                    unsupported_details.append({
                        "type": ctype,
                        "reason": getattr(
                            ctrl, "unsupported_reason",
                            "unsupported runtime trigger expression",
                        ),
                    })
            else:
                if getattr(ctrl, "ignored_noop", False):
                    continue
                unsupported.append(ctype)
                unsupported_details.append({
                    "type": ctype,
                    "reason": getattr(
                        ctrl, "unsupported_reason", "unsupported parameters",
                    ),
                })

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
                if attach_runtime_trigger_expression(controller, ctrl):
                    controllers.append(
                        attach_target_query_selector(controller, ctrl)
                    )
                    projectiles.append(projectile)
                    projectile_hitdefs.append(projectile_hitdef)
                else:
                    unsupported.append(ctype)
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
                if attach_runtime_trigger_expression(controller, ctrl):
                    controllers.append(
                        attach_target_query_selector(controller, ctrl)
                    )
                    projectile_mods.append(projectile_mod)
                else:
                    unsupported.append(ctype)
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
                try:
                    compiled = compile_runtime_controller(state.number, ctrl)
                except ValueError:
                    compiled = None
                if compiled is not None:
                    if ctrl.runtime_trigger_expr is not None:
                        compiled["trigger_expr"] = ctrl.runtime_trigger_expr
                    controllers.append(
                        attach_target_query_selector(compiled, ctrl)
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

    hitcount_persist, hitcount_persist_expr = integer_or_runtime_expr(
        sd.get("hitcountpersist"), 0)
    spr_priority, spr_priority_expr = integer_or_runtime_expr(
        sd.get("sprpriority"), 0)

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
        "spr_priority": spr_priority,
        "spr_priority_expr": spr_priority_expr,
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
        "hitcount_persist": hitcount_persist,
        "hitcount_persist_expr": hitcount_persist_expr,
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
        "unsupported_details": unsupported_details,
    }

    return (
        state_row, hitdefs, sounds, controllers, helpers, explods,
        projectiles, projectile_mods, reversals, hitoverrides
    )
