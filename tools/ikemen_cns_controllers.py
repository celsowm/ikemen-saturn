"""Compile CNS runtime controller records."""
from __future__ import annotations

import re
try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section


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
        "pause",
        "superpause",
        "nothitby",
        "envshake",
        "afterimage",
        "afterimagetime",
        "palfx",
        "assertspecial",
        "makedust",
        "gravity",
        "poweradd",
    }
    if ctype not in supported:
        return None

    ctrl.runtime_trigger_expr = None
    ctrl.runtime_value0_expr = None
    ctrl.runtime_value1_expr = None
    try:
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

    flags: list[str] = []
    if integer(ctrl.get("ignorehitpause"), 0):
        flags.append("IK_CNS_CTRL_IGNORE_HIT_PAUSE")

    def flag_expr() -> str:
        return " | ".join(flags) if flags else "0u"

    if ctype == "assertspecial":
        flag = (ctrl.get("flag") or "").strip().lower()
        if flag != "intro":
            return None
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_ASSERT_INTRO",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": 0,
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

    if ctype == "nothitby":
        raw = ctrl.get("value")
        if raw is None:
            raw = ctrl.get("value2")
        state_mask = no_hit_by_state_mask(raw)
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
            "type": "IK_CNS_CTRL_NOT_HIT_BY",
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
            state_no = eval_int(value_text)
            state_expr = None
        except ValueError:
            state_no = 0
            state_expr = compile_cns_expr(value_text, q16=True)
        ctrl.runtime_value0_expr = state_expr
        return {
            "state_number": state_no,
            "type": "IK_CNS_CTRL_CHANGE_STATE",
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": state_no,
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
            anim_expr = compile_cns_expr(value_text, q16=True)
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
        var_is_system = False
        if ctrl.get("v") is not None and ctrl.get("value") is not None:
            var_index = integer(ctrl.get("v"))
            var_value_text = ctrl.get("value")
        else:
            assignments = []
            for key, value in ctrl.values:
                match = re.fullmatch(r"var\((\d+)\)", key.strip(), flags=re.I)
                if match:
                    assignments.append((int(match.group(1)), value, False))
                match = re.fullmatch(r"sysvar\((\d+)\)", key.strip(), flags=re.I)
                if match:
                    assignments.append((int(match.group(1)), value, True))
            if len(assignments) == 1:
                var_index, var_value_text, var_is_system = assignments[0]

        if var_index is None or var_value_text is None:
            return None
        var_count = 4 if var_is_system else 60
        if var_index < 0 or var_index >= var_count:
            raise ValueError(
                f"[{ctrl.name}] {'sysvar' if var_is_system else 'var'} "
                f"index outside 0..{var_count - 1}")
        var_value = integer(var_value_text)
        if var_value < -2147483648 or var_value > 2147483647:
            raise ValueError(f"[{ctrl.name}] var value outside int32")
        return {
            "state_number": state_no,
            "type": (
                "IK_CNS_CTRL_SYSVAR_SET" if var_is_system else
                "IK_CNS_CTRL_VAR_SET" if ctype == "varset" else
                "IK_CNS_CTRL_VAR_ADD"
            ),
            "trigger_kind": trig_kind,
            "trigger_value": trig_value,
            "trigger_value2": trig_value2,
            "value0": var_index,
            "value1": var_value,
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

def compile_helper_controller(
    state_no: int,
    ctrl: Section,
    helper_index: int,

    *,
    services: dict) -> tuple[dict, dict] | None:
    controller_trigger = services['controller_trigger']
    integer = services['integer']
    pair = services['pair']
    q8 = services['q8']
    supported_keys = {
        "type", "helpertype", "postype", "ownpal", "stateno",
        "keyctrl", "id", "pos", "facing", "ignorehitpause",
        "pausemovetime", "supermovetime",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported_keys:
            return None

    helper_type = (ctrl.get("helpertype", "normal") or "normal").strip().lower()
    if helper_type not in ("normal", ""):
        return None

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_HELPER_POS_P1",
        "p2": "IK_CNS_HELPER_POS_P2",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return None

    trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, "helper")
    px, py = pair(ctrl.get("pos"), 0, 0)
    facing = integer(ctrl.get("facing"), 1)
    if facing == 0:
        facing = 1
    facing = 1 if facing > 0 else -1

    helper = {
        "id": integer(ctrl.get("id"), 0),
        "state_no": integer(ctrl.get("stateno"), 0),
        "pos_x_q8": q8(px),
        "pos_y_q8": q8(py),
        "facing": facing,
        "postype": postype,
        # MUGEN booleans commonly use 99999 for true. These fields are
        # represented as uint8_t flags in the runtime, so preserve truth
        # semantics instead of truncating the source integer (99999 -> 159).
        "keyctrl": int(integer(ctrl.get("keyctrl"), 0) != 0),
        "ownpal": int(integer(ctrl.get("ownpal"), 0) != 0),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_HELPER",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": helper_index,
        "value1": 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    return controller, helper

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
        "p1_spr_priority": integer(ctrl.get("p1sprpriority"), -128),
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
        "chain_id": integer(ctrl.get("chainid"), -1),
        "no_chain_id": integer(
            (ctrl.get("nochainid") or "-1").split(",", 1)[0], -1),
        "no_chain_id2": integer(
            (ctrl.get("nochainid") or "-1,-1").split(",", 1)[1]
            if "," in (ctrl.get("nochainid") or "") else "-1",
            -1),
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

def compile_explod_controller(
    state_no: int,
    ctrl: Section,
    explod_index: int,

    *,
    services: dict) -> tuple[dict, dict] | None:
    controller_trigger = services['controller_trigger']
    integer = services['integer']
    pair = services['pair']
    q8 = services['q8']
    supported_keys = {
        "type", "anim", "postype", "pos", "velocity", "accel",
        "removetime", "sprpriority", "persistent", "ignorehitpause",
        "ownpal", "pausemovetime", "supermovetime", "bindtime",
        "removeongethit", "removeonchangestate", "facing", "vfacing",
        "scale", "trans", "alpha",
    }
    for key, _ in ctrl.values:
        lowered = key.strip().lower()
        if lowered.startswith("trigger"):
            continue
        if lowered not in supported_keys:
            return None

    postype_name = (ctrl.get("postype", "p1") or "p1").strip().lower()
    postypes = {
        "p1": "IK_CNS_HELPER_POS_P1",
        "p2": "IK_CNS_HELPER_POS_P2",
    }
    postype = postypes.get(postype_name)
    if postype is None:
        return None

    trig_kind, trig_value, trig_value2 = controller_trigger(ctrl, "explod")
    px, py = pair(ctrl.get("pos"), 0, 0)
    vx, vy = pair(ctrl.get("velocity"), 0, 0)
    ax, ay = pair(ctrl.get("accel"), 0, 0)
    sx, sy = pair(ctrl.get("scale"), 1, 1)

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
        return None

    alpha_src, _alpha_dst = pair(ctrl.get("alpha"), 256, 256)
    alpha_value = max(0, min(255, int(round(float(alpha_src) * 255.0 / 256.0))))

    explod = {
        "anim_no": integer(ctrl.get("anim"), 0),
        "pos_x_q8": q8(px, wide=True),
        "pos_y_q8": q8(py, wide=True),
        "vel_x_q8": q8(vx, wide=True),
        "vel_y_q8": q8(vy, wide=True),
        "accel_x_q8": q8(ax, wide=True),
        "accel_y_q8": q8(ay, wide=True),
        "remove_time": integer(ctrl.get("removetime"), -1),
        "spr_priority": integer(ctrl.get("sprpriority"), 0),
        "postype": postype,
        "ownpal": integer(ctrl.get("ownpal"), 0),
        "pause_move_time": max(0, integer(ctrl.get("pausemovetime"), 0)),
        "super_move_time": max(0, integer(ctrl.get("supermovetime"), 0)),
        "bind_time": integer(ctrl.get("bindtime"), 0),
        "remove_on_gethit": integer(ctrl.get("removeongethit"), 0),
        "remove_on_state_change": integer(
            ctrl.get("removeonchangestate"), 0),
        "facing": 1 if integer(ctrl.get("facing"), 1) >= 0 else -1,
        "vfacing": 1 if integer(ctrl.get("vfacing"), 1) >= 0 else -1,
        "scale_x_q8": q8(sx),
        "scale_y_q8": q8(sy),
        "trans_mode": trans_map[trans_text],
        "alpha": alpha_value,
    }
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
