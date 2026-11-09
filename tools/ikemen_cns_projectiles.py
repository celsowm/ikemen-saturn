"""Compile CNS projectiles controller records."""
from __future__ import annotations

try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section


def guard_times(ctrl: Section,
    *,
    services: dict) -> tuple[int, int, int]:
    """(hittime, slidetime, ctrltime) of a guarded hit.

    Mugen characters (classic KFM) default guard.hittime to ground.slidetime,
    not ground.hittime as documented; Ikemen's engine does the same for them.
    """
    eval_int = services['eval_int']
    hit = eval_int(ctrl.get("guard.hittime"),
                  eval_int(ctrl.get("ground.slidetime"), 0))
    slide = eval_int(ctrl.get("guard.slidetime"), hit)
    return hit, slide, eval_int(ctrl.get("guard.ctrltime"), slide)

def guard_times_runtime(
    ctrl: Section,
    ground_slide: int,
    ground_slide_expr: list[dict] | None,

    *,
    services: dict) -> tuple[tuple[int, int, int], tuple[list[dict] | None, ...]]:
    """Compile guarded hit clocks, preserving MUGEN's inherited defaults."""
    integer_or_runtime_expr = services['integer_or_runtime_expr']
    _split_top_level = services['_split_top_level']
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

    *,
    services: dict) -> dict:
    GROUND_TYPE = services['GROUND_TYPE']
    anim_type_code = services['anim_type_code']
    attack_attr_mask = services['attack_attr_mask']
    attack_state_mask = services['attack_state_mask']
    dist_fields = services['dist_fields']
    fall_anim_type_code = services['fall_anim_type_code']
    guard_mask = services['guard_mask']
    guard_times = services['guard_times']
    hit_mask = services['hit_mask']
    integer = services['integer']
    integer_or_runtime_expr = services['integer_or_runtime_expr']
    _split_top_level = services['_split_top_level']
    number = services['number']
    pair = services['pair']
    power_fields = services['power_fields']
    priority_type_code = services['priority_type_code']
    q16 = services['q16']
    q8 = services['q8']
    sound_pair = services['sound_pair']
    spark_pair = services['spark_pair']
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
    attack_states = attack_state_mask(
        attr_parts[0] if attr_parts else "S"
    )
    p1_spr_priority, p1_spr_priority_expr = integer_or_runtime_expr(
        ctrl.get("p1sprpriority"), -128)
    no_chain_parts = _split_top_level(ctrl.get("nochainid") or "-1,-1")
    no_chain_parts = (no_chain_parts + ["-1", "-1"])[:2]
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
        "p1_spr_priority": p1_spr_priority,
        "_p1_spr_priority_expr": p1_spr_priority_expr,
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
        "attack_state_mask": attack_states,
        "fall_damage": integer(ctrl.get("fall.damage"), 0),
        "envshake_time": integer(ctrl.get("envshake.time"), 0),
        "envshake_ampl": integer(ctrl.get("envshake.ampl"), 0),
        "envshake_freq": integer(ctrl.get("envshake.freq"), 60),
        "fall_envshake_time": integer(ctrl.get("fall.envshake.time"), 0),
        "fall_envshake_ampl": integer(ctrl.get("fall.envshake.ampl"), 0),
        "fall_envshake_freq": integer(ctrl.get("fall.envshake.freq"), 60),
        "id": integer(ctrl.get("id"), 0),
        "chain_id": integer_or_runtime_expr(ctrl.get("chainid"), -1)[0],
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

def compile_projectile_controller(
    state_no: int,
    ctrl: Section,
    projectile_index: int,
    hitdef_global: int,
    default_spark_no: int,
    default_guard_spark_no: int,

    *,
    services: dict) -> tuple[dict, dict, dict] | None:
    _projectile_hitdef_row = services['_projectile_hitdef_row']
    _split_top_level = services['_split_top_level']
    controller_trigger = services['controller_trigger']
    integer = services['integer']
    pair = services['pair']
    q8 = services['q8']
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

    *,
    services: dict) -> tuple[dict, dict] | None:
    controller_trigger = services['controller_trigger']
    integer = services['integer']
    pair = services['pair']
    q8 = services['q8']
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
