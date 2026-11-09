"""Compile CNS runtime controller records."""
from __future__ import annotations

import re
try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section

try:
    from .ikemen_cns_helpers import compile_helper_controller
    from .ikemen_cns_projectiles import (
        guard_times, guard_times_runtime, _projectile_hitdef_row,
        compile_projectile_controller, compile_modify_projectile_controller,
    )
    from .ikemen_cns_explods import compile_explod_controller
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_helpers import compile_helper_controller
    from ikemen_cns_projectiles import (
        guard_times, guard_times_runtime, _projectile_hitdef_row,
        compile_projectile_controller, compile_modify_projectile_controller,
    )
    from ikemen_cns_explods import compile_explod_controller



def compile_runtime_controller(
    state_no: int,
    ctrl: Section,

    *,
    services: dict) -> dict | None:
    MOVE_TYPE = services['MOVE_TYPE']
    PHYSICS = services['PHYSICS']
    STATE_TYPE = services['STATE_TYPE']
    STRICT_CONVERSION = services['STRICT_CONVERSION']
    _split_top_level = services['_split_top_level']
    compile_cns_expr = services['compile_cns_expr']
    compile_controller_trigger_expr = services['compile_controller_trigger_expr']
    controller_requires_runtime_expr = services['controller_requires_runtime_expr']
    controller_trigger = services['controller_trigger']
    eval_int = services['eval_int']
    integer = services['integer']
    no_hit_by_attr_mask = services['no_hit_by_attr_mask']
    no_hit_by_state_mask = services['no_hit_by_state_mask']
    number = services['number']
    pair = services['pair']
    pair_runtime_expr = services['pair_runtime_expr']
    q16 = services['q16']
    q8 = services['q8']
    ctype = (ctrl.get("type", "") or "").strip().lower()

    supported = {
        "changestate",
        "ctrlset",
        "posadd",
        "posset",
        "sprpriority",
        "changeanim",
        "changeanim2",
        "statetypeset",
        "width",
        "varset",
        "varadd",
        "varrandom",
        "lifeadd",
        "sysfvarset",
        "sysfvaradd",
        "targetbind",
        "targetfacing",
        "targetlifeadd",
        "targetstate",
        "targetdrop",
        "screenbound",
        "turn",
        "selfstate",
        "veladd",
        "velset",
        "velmul",
        "hitvelset",
        "posfreeze",
        "destroyself",
        "removeexplod",
        "pause",
        "superpause",
        "nothitby",
        "hitby",
        "envshake",
        "envcolor",
        "afterimage",
        "afterimagetime",
        "palfx",
        "assertspecial",
        "makedust",
        "gravity",
        "poweradd",
        "playerpush",
    }
    if ctype not in supported:
        return None

    ctrl.runtime_trigger_expr = None
    ctrl.runtime_value0_expr = None
    ctrl.runtime_value1_expr = None
    try:
        if controller_requires_runtime_expr(ctrl):
            raise ValueError("combined controller trigger expression")
        trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, ctype)
    except ValueError:
        ctrl.runtime_trigger_expr = compile_controller_trigger_expr(ctrl)
        trig_kind, trig_value, trig_value2 = "IK_CNS_TRIGGER_ALWAYS", 0, 0
    if trig_kind == "IK_CNS_TRIGGER_ALWAYS":
        trigger_texts = [
            expr.strip().casefold()
            for trigger_index in range(1, 9)
            for expr in ctrl.all(f"trigger{trigger_index}")
        ]
        if trigger_texts and any(
            expr not in {"1", "1.0", "true"} for expr in trigger_texts
        ):
            try:
                ctrl.runtime_trigger_expr = compile_controller_trigger_expr(ctrl)
            except ValueError:
                if STRICT_CONVERSION:
                    raise
                # A trigger we cannot represent must never become an
                # unconditional controller. The caller records this
                # controller as deferred when None is returned.
                return None

    flags: list[str] = []
    if integer(ctrl.get("ignorehitpause"), 0):
        flags.append("IK_CNS_CTRL_IGNORE_HIT_PAUSE")

    def flag_expr() -> str:
        return " | ".join(flags) if flags else "0u"

    if ctype == "assertspecial":
        flag = (ctrl.get("flag") or "").strip().casefold()
        if flag in {"nowalk", "noautoturn"}:
            flag_value = (
                "IK_CNS_ASSERT_NO_WALK" if flag == "nowalk" else
                "IK_CNS_ASSERT_NO_AUTO_TURN"
            )
            controller_type = "IK_CNS_CTRL_ASSERT_WALK_FLAGS"
        elif flag == "intro":
            flag_value = "0"
            controller_type = "IK_CNS_CTRL_ASSERT_INTRO"
        elif flag == "roundnotover":
            flag_value = "0"
            controller_type = "IK_CNS_CTRL_ASSERT_ROUND_NOT_OVER"
        else:
            return None
        return {
            "state_number": state_no,
            "type": controller_type,
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": flag_value,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "makedust":
        pos = pair(ctrl.get("pos"), 0, 0)
        spacing = integer(ctrl.get("spacing"), 0)
        if spacing not in (0, 1):
            return None
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_MAKE_DUST",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("anim"), 0),
            "value1": int(pos[0]),
            "value2": int(pos[1]),
            "flags": flag_expr(),
        }

    if ctype == "gravity":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_GRAVITY",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "playerpush":
        for key, _ in ctrl.values:
            lowered = key.strip().casefold()
            if lowered.startswith("trigger") or lowered in {
                "type", "value", "ignorehitpause",
            }:
                continue
            return None
        value_text = ctrl.get("value") or "1"
        try:
            value = integer(value_text)
            value_expr = None
        except ValueError:
            value = 0
            value_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = value_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_PLAYER_PUSH",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": value,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "lifeadd":
        supported_keys = {
            "type", "value", "kill", "absolute", "ignorehitpause",
        }
        if any(
            not key.strip().casefold().startswith("trigger") and
            key.strip().casefold() not in supported_keys
            for key, _ in ctrl.values
        ):
            return None
        value, value_expr = services["integer_or_runtime_expr"](
            ctrl.get("value"), 0)
        ctrl.runtime_value0_expr = value_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_LIFE_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": value,
            # The current fight model has a fixed 1.0 defense multiplier, so
            # LifeAdd's absolute switch has no numeric effect yet.
            "value1": int(integer(ctrl.get("absolute"), 0) != 0),
            "value2": int(integer(ctrl.get("kill"), 1) != 0),
            "flags": flag_expr(),
        }

    if ctype == "poweradd":
        value_text = ctrl.get("value") or "0"
        try:
            value = eval_int(value_text)
            value_expr = None
        except ValueError:
            value = 0
            value_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = value_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POWER_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": value,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "palfx":
        def pack_rgb(text: str | None) -> int:
            parts = _split_top_level(text or "0,0,0")
            while len(parts) < 3:
                parts.append("0")
            values = [
                max(-255, min(255, integer(p, 0)))
                for p in parts[:3]
            ]
            return (
                (values[0] & 0x1ff) |
                ((values[1] & 0x1ff) << 9) |
                ((values[2] & 0x1ff) << 18)
            )

        sin_parts = _split_top_level(ctrl.get("sinadd") or "0,0,0,1")
        while len(sin_parts) < 4:
            sin_parts.append("0")
        sin_cycle = max(1, integer(sin_parts[3], 1))

        mul_parts = _split_top_level(ctrl.get("mul") or "256,256,256")
        while len(mul_parts) < 3:
            mul_parts.append("256")
        mul_values = [
            max(0, min(511, integer(part, 256)))
            for part in mul_parts[:3]
        ]
        mul_packed = (
            (mul_values[0] & 0x1ff) |
            ((mul_values[1] & 0x1ff) << 9) |
            ((mul_values[2] & 0x1ff) << 18)
        )

        sinmul_parts = _split_top_level(ctrl.get("sinmul") or "0,0,0,1")
        while len(sinmul_parts) < 4:
            sinmul_parts.append("0")
        sinmul_values = [
            max(-255, min(255, integer(part, 0)))
            for part in sinmul_parts[:3]
        ]
        sinmul_packed = (
            (sinmul_values[0] & 0x1ff) |
            ((sinmul_values[1] & 0x1ff) << 9) |
            ((sinmul_values[2] & 0x1ff) << 18)
        )
        sinmul_cycle = max(1, integer(sinmul_parts[3], 1))

        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_PAL_FX",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": pack_rgb(ctrl.get("add")),
            "value2": pack_rgb(",".join(sin_parts[:3])),
            "value3": sin_cycle,
            "value4": mul_packed,
            "value5": sinmul_packed,
            "value6": sinmul_cycle,
            "flags": flag_expr(),
        }

    if ctype == "afterimage":
        def pack_rgb_signed(text: str | None, defaults: tuple[int, int, int]) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            values = list(defaults)
            for i, part in enumerate(parts[:3]):
                values[i] = max(-128, min(127, integer(part, values[i])))
            packed = (
                (values[0] & 0xff) |
                ((values[1] & 0xff) << 8) |
                ((values[2] & 0xff) << 16)
            )
            return packed if packed < 0x80000000 else packed - 0x100000000

        def pack_rgb_unsigned(text: str | None, defaults: tuple[int, int, int]) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            values = list(defaults)
            for i, part in enumerate(parts[:3]):
                values[i] = max(0, min(255, integer(part, values[i])))
            return values[0] | (values[1] << 8) | (values[2] << 16)

        def pack_mul(text: str | None) -> int:
            parts = [
                p for p in _split_top_level(text or "") if p.strip()
            ]
            defaults = [1.0, 1.0, 1.0]
            values = defaults[:]
            for i, part in enumerate(parts[:3]):
                values[i] = max(0.0, min(1.0, number(part)))
            q = [max(0, min(255, int(round(v * 255.0)))) for v in values]
            return q[0] | (q[1] << 8) | (q[2] << 16)

        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_AFTER_IMAGE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": integer(ctrl.get("length"), 20),
            "value2": integer(ctrl.get("timegap"), 1),
            "value3": integer(ctrl.get("framegap"), 4),
            "value4": pack_rgb_signed(ctrl.get("palbright"), (30, 30, 30)),
            "value5": pack_rgb_unsigned(ctrl.get("palcontrast"), (120, 120, 220)),
            "value6": pack_rgb_signed(ctrl.get("paladd"), (10, 10, 25)),
            "value7": pack_mul(
                ctrl.get("palmul") or ".65,.65,.75"
            ),
            "flags": flag_expr(),
        }

    if ctype == "afterimagetime":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_AFTER_IMAGE_TIME",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 1),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "envshake":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_ENV_SHAKE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 0),
            "value1": integer(ctrl.get("ampl"), 0),
            "flags": flag_expr(),
        }

    if ctype == "envcolor":
        color_text = ctrl.get("value")
        if color_text is None:
            raise ValueError(f"[{ctrl.name}] EnvColor requires value=r,g,b")
        color_parts = _split_top_level(color_text)
        if len(color_parts) != 3:
            raise ValueError(f"[{ctrl.name}] EnvColor value must have 3 channels")
        rgb = []
        for part in color_parts:
            channel = integer(part)
            if channel < 0 or channel > 255:
                raise ValueError(f"[{ctrl.name}] EnvColor channel outside 0..255")
            rgb.append(channel)
        time = integer(ctrl.get("time"), 1)
        if time < -1 or time > 65535:
            raise ValueError(f"[{ctrl.name}] EnvColor time outside -1..65535")
        under = integer(ctrl.get("under"), 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_ENV_COLOR",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": (rgb[0] << 16) | (rgb[1] << 8) | rgb[2],
            "value1": time,
            "value2": int(under != 0),
            "value3": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
            "flags": flag_expr(),
        }

    if ctype == "superpause":
        if integer(ctrl.get("darken"), 1):
            flags.append("IK_CNS_CTRL_SUPER_DARKEN")
        if ctrl.get("anim") is not None:
            flags.append("IK_CNS_CTRL_HAS_SUPER_ANIM")
        pos_x, pos_y = pair(ctrl.get("pos"), 0, 0)
        packed_pos = ((int(pos_x) & 0xffff) << 16) | (int(pos_y) & 0xffff)
        if packed_pos >= 0x80000000:
            packed_pos -= 0x100000000
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SUPER_PAUSE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 30),
            "value1": integer(ctrl.get("poweradd"), 0),
            "value2": integer(ctrl.get("anim"), -1),
            "value3": packed_pos,
            "value4": integer(ctrl.get("movetime"), 0),
            "value5": integer(ctrl.get("endcmdbuftime"), 0),
            "value6": integer(ctrl.get("pausebg"), 1),
            "value7": integer(ctrl.get("brightness"), 0),
            "flags": flag_expr(),
        }

    if ctype == "pause":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_PAUSE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("time"), 0),
            "value1": integer(ctrl.get("movetime"), 0),
            "value2": integer(ctrl.get("endcmdbuftime"), 0),
            "value3": integer(ctrl.get("pausebg"), 1),
            "flags": flag_expr(),
        }

    if ctype in {"hitby", "nothitby"}:
        raw = ctrl.get("value")
        if raw is None:
            raw = ctrl.get("value2")
        state_mask = (
            services["hit_by_state_mask"](raw)
            if ctype == "hitby" else no_hit_by_state_mask(raw)
        )
        attr_mask = no_hit_by_attr_mask(raw)
        if state_mask == "0u" and attr_mask == "0u":
            return None
        packed = (
            f"({state_mask}) | (({attr_mask}) << 8)"
            if attr_mask != "0u"
            else state_mask
        )
        return {
            "state_number": state_no,
            "type": (
                "IK_CNS_CTRL_HIT_BY" if ctype == "hitby" else
                "IK_CNS_CTRL_NOT_HIT_BY"
            ),
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": packed,
            "value1": integer(ctrl.get("time"), 1),
            "flags": flag_expr(),
        }

    if ctype == "changestate":
        has_ctrl = ctrl.get("ctrl") is not None
        if has_ctrl:
            flags.append("IK_CNS_CTRL_HAS_CTRL")
        value_text = ctrl.get("value") or "-1"
        try:
            target_state_no = eval_int(value_text)
            state_expr = None
        except ValueError:
            target_state_no = 0
            state_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = state_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": target_state_no,
            "value1": integer(ctrl.get("ctrl"), 0),
            "flags": flag_expr(),
        }

    if ctype == "ctrlset":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CTRL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "flags": flag_expr(),
        }

    if ctype == "posadd":
        x_text = (ctrl.get("x") or "0").strip()
        m = re.fullmatch(
            r"(-?\d+)\s*-\s*BackEdgeBodyDist",
            x_text,
            flags=re.I,
        )
        if m and ctrl.get("y") is None:
            return {
                "state_number": state_no,
                "type": "IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE",
                "trigger_kind": trig_kind,
                "trigger_value": trig_value,
                "trigger_value2": trig_value2,
                "value0": q8(float(m.group(1))),
                "value1": 0,
                "flags": flag_expr(),
            }
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{x_text},{ctrl.get('y') or '0'}", 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value2": integer(ctrl.get("id"), -1),
            "flags": flag_expr(),
        }

    if ctype == "posset":
        x = number(ctrl.get("x"), 0)
        y = number(ctrl.get("y"), 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis.append("IK_CNS_CTRL_AXIS_X")
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "sprpriority":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SPR_PRIORITY",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "changeanim":
        value_text = ctrl.get("value") or "-1"
        try:
            anim_no = eval_int(value_text)
            anim_expr = None
        except ValueError:
            anim_no = 0
            anim_expr = compile_cns_expr(value_text)
        ctrl.runtime_value0_expr = anim_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_ANIM",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": anim_no,
            "value1": integer(ctrl.get("elem"), 1),
            "flags": flag_expr(),
        }

    if ctype == "changeanim2":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_ANIM2",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 1,
            "flags": flag_expr(),
        }

    if ctype == "statetypeset":
        state_type = (ctrl.get("statetype") or "U").strip().upper()
        move_type = (ctrl.get("movetype") or "U").strip().upper()
        physics = (ctrl.get("physics") or "U").strip().upper()
        set_flags = []
        if state_type not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_STATE_TYPE")
        if move_type not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_MOVE_TYPE")
        if physics not in ("", "U"):
            set_flags.append("IK_CNS_CTRL_SET_PHYSICS")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_STATE_TYPE_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": STATE_TYPE.get(state_type, "IK_CNS_STATE_UNCHANGED"),
            "value1": MOVE_TYPE.get(move_type, "IK_CNS_MOVE_UNCHANGED"),
            "value2": PHYSICS.get(physics, "IK_CNS_PHYS_BY_TYPE"),
            "value3": " | ".join(set_flags) if set_flags else "0u",
            "flags": flag_expr(),
        }

    if ctype in ("varset", "varadd"):
        if ctype == "varset":
            var2 = ctrl.get("var(2)")
            if var2 is not None and re.fullmatch(
                r'command\s*=\s*"holdfwd"', var2.strip(), flags=re.I
            ):
                return {
                    "state_number": state_no,
                    "type": "IK_CNS_CTRL_CAPTURE_COMMAND_AXIS",
                    "trigger_kind": trig_kind,
                    "trigger_value": trig_value,
                    "trigger_value2": trig_value2,
                    "value0": 0,
                    "value1": 0,
                    "flags": flag_expr(),
                }

        var_index = None
        var_value_text = None
        var_is_system = ctype in {"sysfvarset", "sysfvaradd"}
        var_is_float = ctype in {"sysfvarset", "sysfvaradd"}
        if ctrl.get("v") is not None and ctrl.get("value") is not None:
            var_index = integer(ctrl.get("v"))
            var_value_text = ctrl.get("value")
        else:
            assignments = []
            for key, value in ctrl.values:
                match = re.fullmatch(
                    r"(sysfvar|sysvar|fvar|var)\((\d+)\)",
                    key.strip(), flags=re.I)
                if match:
                    kind = match.group(1).casefold()
                    assignments.append((
                        int(match.group(2)), value,
                        kind.startswith("sys"),
                        kind.endswith("fvar"),
                    ))
            if len(assignments) == 1:
                (var_index, var_value_text,
                 var_is_system, var_is_float) = assignments[0]

        if var_index is None or var_value_text is None:
            return None
        if var_is_system:
            var_count = 5
        else:
            var_count = 40 if var_is_float else 60
        if var_index < 0 or var_index >= var_count:
            variable_kind = (
                "sysfvar" if var_is_system and var_is_float else
                "sysvar" if var_is_system else
                "fvar" if var_is_float else "var"
            )
            raise ValueError(
                f"[{ctrl.name}] "
                f"{variable_kind} "
                f"index outside 0..{var_count - 1}")
        try:
            var_value = (
                q16(number(var_value_text)) if var_is_float else
                integer(var_value_text)
            )
            var_value_expr = None
        except ValueError:
            try:
                # Float-variable expressions use Q16.16, while integer VarSet
                # and SysVarSet expressions retain their full int32 range.
                var_value_expr = compile_cns_expr(
                    var_value_text, q16=var_is_float)
                var_value = 0
            except ValueError:
                if STRICT_CONVERSION:
                    raise
                return None
        if var_value < -2147483648 or var_value > 2147483647:
            raise ValueError(f"[{ctrl.name}] var value outside int32")
        ctrl.runtime_value1_expr = var_value_expr
        if var_is_system and var_is_float:
            variable_controller = (
                "IK_CNS_CTRL_SYSFVAR_ADD"
                if ctype in {"sysfvaradd", "varadd"} else
                "IK_CNS_CTRL_SYSFVAR_SET"
            )
        elif var_is_system:
            variable_controller = (
                "IK_CNS_CTRL_SYSVAR_ADD" if ctype == "varadd" else
                "IK_CNS_CTRL_SYSVAR_SET"
            )
        elif var_is_float:
            variable_controller = (
                "IK_CNS_CTRL_FVAR_ADD" if ctype == "varadd" else
                "IK_CNS_CTRL_FVAR_SET"
            )
        else:
            variable_controller = (
                "IK_CNS_CTRL_VAR_SET" if ctype == "varset" else
                "IK_CNS_CTRL_VAR_ADD"
            )
        return {
            "state_number": state_no,
            "type": variable_controller,
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": var_index,
            "value1": var_value,
            "flags": flag_expr(),
        }

    if ctype == "varrandom":
        if ctrl.get("v") is None:
            raise ValueError(f"[{ctrl.name}] varrandom requires v")
        var_index = integer(ctrl.get("v"))
        if not 0 <= var_index < 60:
            raise ValueError(f"[{ctrl.name}] var index outside 0..59")
        range_values = _split_top_level(ctrl.get("range") or "0,999")
        if len(range_values) == 1:
            range_min = 0
            range_max = integer(range_values[0])
        elif len(range_values) == 2:
            range_min = integer(range_values[0])
            range_max = integer(range_values[1])
        else:
            raise ValueError(
                f"[{ctrl.name}] varrandom range must have one or two values")
        if range_min > range_max:
            range_min, range_max = range_max, range_min
        if range_min < -2147483648 or range_max > 2147483647:
            raise ValueError(f"[{ctrl.name}] varrandom range outside int32")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VAR_RANDOM",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": var_index,
            "value1": range_min,
            "value2": range_max,
            "flags": flag_expr(),
        }

    if ctype == "screenbound":
        # value3 bit 0: `value` given, bit 1: `movecamera` given.
        move = ctrl.get("movecamera")
        move_x, move_y = pair(move, 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SCREEN_BOUND",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value"), 0),
            "value1": int(move_x),
            "value2": int(move_y),
            "value3": int(ctrl.get("value") is not None) |
                      (int(move is not None) << 1),
            "flags": flag_expr(),
        }

    if ctype == "targetdrop":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_DROP",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("excludeid"), -1),
            "value1": integer(ctrl.get("keepone"), 1),
            "value7": (
                integer(
                    re.search(
                        r"NumTarget\s*\(\s*(-?\d+)\s*\)",
                        " ".join(ctrl.all("trigger1")),
                        flags=re.I,
                    ).group(1)
                )
                if re.search(
                    r"NumTarget\s*\(\s*(-?\d+)\s*\)",
                    " ".join(ctrl.all("trigger1")),
                    flags=re.I,
                )
                else -1
            ),
            "flags": flag_expr(),
        }

    if ctype == "targetbind":
        x, y = pair(ctrl.get("pos"), 0, 0)
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_BIND",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetfacing":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_FACING",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value"), 1),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetlifeadd":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_LIFE_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "targetstate":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TARGET_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "value2": integer(ctrl.get("id"), -1),
            "value3": integer(ctrl.get("index"), -1),
            "flags": flag_expr(),
        }

    if ctype == "turn":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_TURN",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "posfreeze":
        flags2: list[str] = []
        if ctrl.get("x") is None and ctrl.get("y") is None:
            # MUGEN PosFreeze defaults to freezing both axes.
            flags2 += ["IK_CNS_CTRL_AXIS_X", "IK_CNS_CTRL_AXIS_Y"]
        else:
            if integer(ctrl.get("x"), 0):
                flags2.append("IK_CNS_CTRL_AXIS_X")
            if integer(ctrl.get("y"), 0):
                flags2.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_POS_FREEZE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": " | ".join(flags2 + flags) if flags2 or flags else "0u",
        }

    if ctype == "destroyself":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_DESTROY_SELF",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "removeexplod":
        for key, _ in ctrl.values:
            lowered = key.strip().lower()
            if lowered.startswith("trigger") or lowered in {
                    "type", "id", "persistent", "ignorehitpause"}:
                continue
            return None
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_REMOVE_EXPLOD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("id"), -1),
            "value1": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
            "flags": flag_expr(),
        }

    if ctype == "selfstate":
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_SELF_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": integer(ctrl.get("value")),
            "value1": 0,
            "flags": flag_expr(),
        }

    if ctype == "veladd":
        x_text = ctrl.get("x")
        y_text = ctrl.get("y")
        use_yaccel = bool(
            y_text is not None and re.fullmatch(
                r"Const\s*\(\s*movement\.yaccel\s*\)",
                y_text.strip(),
                flags=re.I,
            )
        )
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{x_text or '0'},"
                f"{'0' if use_yaccel else (y_text or '0')}", 0, 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis.append("IK_CNS_CTRL_AXIS_X")
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        if use_yaccel:
            flags.append("IK_CNS_CTRL_USE_YACCEL")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_ADD",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value4": q16(x),
            "value5": q16(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "velset":
        x, y, ctrl.runtime_value0_expr, ctrl.runtime_value1_expr = \
            pair_runtime_expr(
                f"{ctrl.get('x') or '0'},{ctrl.get('y') or '0'}", 0, 0)
        axis: list[str] = []
        if ctrl.get("x") is not None:
            axis += ["IK_CNS_CTRL_AXIS_X", "IK_CNS_CTRL_LOCAL_X"]
        if ctrl.get("y") is not None:
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": q8(x),
            "value1": q8(y),
            "value4": q16(x),
            "value5": q16(y),
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "hitvelset":
        axis: list[str] = []
        if integer(ctrl.get("x"), 0):
            axis.append("IK_CNS_CTRL_AXIS_X")
        if integer(ctrl.get("y"), 0):
            axis.append("IK_CNS_CTRL_AXIS_Y")
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_HIT_VEL_SET",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
            "value1": 0,
            "flags": " | ".join(axis + flags) if axis or flags else "0u",
        }

    if ctype == "velmul":
        plain = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
        xtext = (ctrl.get("x") or "").strip()
        ytext = (ctrl.get("y") or "").strip()
        if (xtext or ytext) and all(
            not t or plain.fullmatch(t) for t in (xtext, ytext)
        ):
            axis = []
            if xtext:
                axis.append("IK_CNS_CTRL_AXIS_X")
            if ytext:
                axis.append("IK_CNS_CTRL_AXIS_Y")
            return {
                "state_number": state_no,
                "type": "IK_CNS_CTRL_VEL_MUL",
                "trigger_kind": trig_kind,
                "trigger_value": trig_value,
                "trigger_value2": trig_value2,
                "value0": q8(number(xtext or None, 1)),
                "value1": q8(number(ytext or None, 1)),
                "flags": " | ".join(axis + flags) if flags else
                         " | ".join(axis),
            }
        xexpr = (ctrl.get("x") or "").strip()
        m = re.fullmatch(
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\*\s*"
            r"ifelse\s*\(\s*AnimElemTime\s*\(\s*(\d+)\s*\)"
            r"\s*<\s*0\s*,\s*1\s*,\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)",
            xexpr,
            flags=re.I,
        )
        if not m or ctrl.get("y") is not None:
            return None
        base = float(m.group(1))
        elem = int(m.group(2))
        tail = float(m.group(3))
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_VEL_MUL_X_BY_ANIM_ELEM",
            "trigger_kind": trig_kind,
            "trigger_value": elem,
            "trigger_value2": 0,
            "value0": q8(base),
            "value1": q8(base * tail),
            "flags": flag_expr(),
        }

    # `value` widens the player box and the screen-edge box, `player` and
    # `edge` only their own.
    value_text = ctrl.get("value")
    player = pair(ctrl.get("player", value_text), 0, 0)
    edge = pair(ctrl.get("edge", value_text), 0, 0)
    if any(int(v) != v for v in (*player, *edge)):
        raise ValueError(
            f"[{ctrl.name}] Width values must be integral in the Saturn subset"
        )
    return {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_WIDTH",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": int(player[0]),
        "value1": int(player[1]),
        "value2": int(edge[0]),
        "value3": int(edge[1]),
        "flags": flag_expr(),
    }
