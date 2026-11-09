"""Compile CNS explods controller records."""
from __future__ import annotations

import re

try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section


def _explod_scale_q8(value: float, q8) -> int:
    # Large authored scales are full-screen overlay sentinels. Keep them
    # representable; the renderer bounds the resulting rectangle.
    bounded = max(-128.0, min(32767 / 256.0, float(value)))
    return q8(bounded)


def compile_explod_controller(
    state_no: int,
    ctrl: Section,
    explod_index: int,

    *,
    services: dict) -> tuple[dict, dict] | None:
    controller_trigger = services['controller_trigger']
    integer = services['integer']
    pair = services['pair']
    pair_runtime_expr = services['pair_runtime_expr']
    integer_or_runtime_expr = services['integer_or_runtime_expr']
    q8 = services['q8']
    def reject(reason: str) -> None:
        ctrl.unsupported_reason = reason
        return None

    supported_keys = {
        "type", "anim", "id", "supermove", "postype", "pos", "random", "vel",
        "velocity", "velset", "accel", "space",
        "removetime", "sprpriority", "persistent", "ignorehitpause",
        "ownpal", "pausemovetime", "supermovetime", "bindtime",
        "pausemove",
        "removeongethit", "removeonchangestate", "facing", "vfacing",
        "face", "scale", "trans", "alpha", "under", "ontop",
        "unhittable", "shadow",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported_keys:
            return reject(f"unsupported parameter {lowered}")

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_EXPLOD_POS_P1",
        "p2": "IK_CNS_EXPLOD_POS_P2",
        "front": "IK_CNS_EXPLOD_POS_FRONT",
        "back": "IK_CNS_EXPLOD_POS_BACK",
        "left": "IK_CNS_EXPLOD_POS_LEFT",
        "right": "IK_CNS_EXPLOD_POS_RIGHT",
        "none": "IK_CNS_EXPLOD_POS_NONE",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return reject(f"unsupported postype {postype_name}")
    space_name = ctrl.get("space")
    if space_name is not None and space_name.strip().lower() != "screen":
        return reject(f"unsupported space {space_name.strip()}")
    unhittable = ctrl.get("unhittable")
    if unhittable is not None and integer(unhittable, 0) != 1:
        return reject(f"unsupported unhittable value {unhittable.strip()}")

    trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, "explod")
    px, py, px_expr, py_expr = pair_runtime_expr(
        ctrl.get("pos"), 0, 0)
    ctrl.runtime_value0_expr = px_expr
    ctrl.runtime_value1_expr = py_expr
    random_x, random_y = pair(ctrl.get("random"), 0, 0)
    shadow_values = [0, 0, 0]
    has_shadow = 0
    if ctrl.get("shadow") is not None:
        raw_shadow = [part.strip() for part in ctrl.get("shadow").split(",")]
        if len(raw_shadow) > 3:
            return reject("shadow has more than three components")
        try:
            values = [integer(value) for value in raw_shadow]
        except ValueError as exc:
            return reject(f"invalid shadow value: {exc}")
        if values == [-1]:
            has_shadow = 1
            values = []
        elif any(value < 0 for value in values):
            return reject("negative shadow component")
        if any(value < 0 or value > 255 for value in values):
            return reject("shadow component outside 0..255")
        shadow_values[:len(values)] = values
        has_shadow |= int(any(shadow_values))
    vx, vy = pair(
        ctrl.get("vel", ctrl.get("velocity", ctrl.get("velset"))), 0, 0)
    ax, ay = pair(ctrl.get("accel"), 0, 0)
    sx, sy, sx_expr, sy_expr = pair_runtime_expr(
        ctrl.get("scale"), 1, 1)

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
        return reject(f"unsupported trans mode {trans_text}")

    alpha_src, _alpha_dst, alpha_src_expr, _alpha_dst_expr = pair_runtime_expr(
        ctrl.get("alpha"), 256, 256)
    alpha_value = max(0, min(255, int(round(float(alpha_src) * 255.0 / 256.0))))

    if ctrl.get("supermovetime") is not None:
        super_move_time = max(0, integer(ctrl.get("supermovetime"), 0))
    else:
        super_move_time = (
            0xFFFFFFFF if integer(ctrl.get("supermove"), 0) else 0
        )
    super_move_time = min(super_move_time, 0xFFFFFFFF)

    anim_text = (ctrl.get("anim") or "0").strip()
    fightfx_prefix = re.match(r"^[fF](?=\s|\(|[A-Za-z_]|[+-]?\d)", anim_text)
    use_fightfx = fightfx_prefix is not None
    anim_expr_text = anim_text
    if fightfx_prefix:
        anim_expr_text = anim_text[1:].strip()
        if anim_expr_text.startswith("(") and anim_expr_text.endswith(")"):
            anim_expr_text = anim_expr_text[1:-1].strip()
    try:
        anim_no = integer(anim_expr_text, 0)
        anim_expr = None
    except ValueError:
        anim_no = 0
        anim_expr = services["compile_cns_expr"](anim_expr_text)
    fightfx_anims = services.get("FIGHTFX_ANIMS")
    if (anim_expr is None and use_fightfx and fightfx_anims is not None and
            anim_no not in fightfx_anims):
        return reject(f"fightfx animation {anim_no} does not exist")
    facing_text = ctrl.get("facing", ctrl.get("face"))
    try:
        facing = 1 if integer(facing_text, 1) >= 0 else -1
        facing_expr = None
    except ValueError:
        facing = 1
        facing_expr = services["compile_cns_expr"](facing_text, q16=True)
    spr_priority, spr_priority_expr = integer_or_runtime_expr(
        ctrl.get("sprpriority"), 0)
    spr_priority = max(-127, min(127, spr_priority))
    bind_time, bind_time_expr = integer_or_runtime_expr(
        ctrl.get("bindtime"), 0)
    bind_time = max(-32768, min(32767, bind_time))
    explod = {
        "anim_no": anim_no,
        "id": max(0, integer(ctrl.get("id"), 0)),
        "pos_x_q8": q8(px, wide=True),
        "pos_y_q8": q8(py, wide=True),
        "vel_x_q8": q8(vx, wide=True),
        "vel_y_q8": q8(vy, wide=True),
        "accel_x_q8": q8(ax, wide=True),
        "accel_y_q8": q8(ay, wide=True),
        "remove_time": integer(ctrl.get("removetime"), -1),
        "spr_priority": spr_priority,
        "postype": postype,
        "ownpal": integer(ctrl.get("ownpal"), int(use_fightfx)),
        "pause_move_time": min(0xFFFFFFFF, max(0, integer(
            ctrl.get("pausemovetime", ctrl.get("pausemove")), 0))),
        "super_move_time": super_move_time,
        "bind_time": bind_time,
        "remove_on_gethit": integer(ctrl.get("removeongethit"), 0),
        "remove_on_state_change": integer(
            ctrl.get("removeonchangestate"), 0),
        "facing": facing,
        "vfacing": 1 if integer(ctrl.get("vfacing"), 1) >= 0 else -1,
        "scale_x_q8": _explod_scale_q8(sx, q8),
        "scale_y_q8": _explod_scale_q8(sy, q8),
        "trans_mode": trans_map[trans_text],
        "alpha": alpha_value,
        "under": 1 if integer(ctrl.get("under"), 0) else 0,
        "ontop": 1 if integer(ctrl.get("ontop"), 0) else 0,
        "random_x_q8": q8(random_x, wide=True),
        "random_y_q8": q8(random_y, wide=True),
        "has_shadow": has_shadow,
        "use_fightfx": int(use_fightfx),
        "_anim_expr": anim_expr,
        "_facing_expr": facing_expr,
        "_spr_priority_expr": spr_priority_expr,
        "_bind_time_expr": bind_time_expr,
        "_scale_x_expr": sx_expr,
        "_scale_y_expr": sy_expr,
        "_alpha_expr": alpha_src_expr,
    }
    # Explod entities are not inserted into the fighter/projectile contact
    # queue, so `unhittable = 1` already matches this runtime's behavior.
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
