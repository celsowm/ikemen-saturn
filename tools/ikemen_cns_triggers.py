"""Compile CNS controller trigger conditions into runtime records."""
from __future__ import annotations

import re
try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct tool invocation
    from ikemen_cns_parse import Section


def compile_controller_trigger(
    ctrl: Section,
    ctype: str,
    *,
    services: dict,
) -> tuple[str, int, int]:
    _anim_elem_range_trigger = services["_anim_elem_range_trigger"]
    _move_contact_window = services["_move_contact_window"]
    _strip_outer_parens = services["_strip_outer_parens"]
    integer = services["integer"]
    q8 = services["q8"]
    simple_trigger = services["simple_trigger"]
    triggers = ctrl.all("trigger1")
    trigger2 = ctrl.all("trigger2")
    trigger3 = ctrl.all("trigger3")

    anim_or: list[str] = []
    for trigger_index in range(1, 9):
        group = ctrl.all(f"trigger{trigger_index}")
        # Lines of one triggerN are ANDed: two different `AnimElem = n` in a
        # group can never both hold, so that group drops out of the OR.
        if len(set(group)) > 1 and all(
                re.fullmatch(r"AnimElem\s*=\s*\d+", g.strip(), flags=re.I)
                for g in group):
            continue
        anim_or.extend(group)
    if 2 <= len(anim_or):
        elems: list[int] = []
        for expr in anim_or:
            m = re.fullmatch(
                r"AnimElem\s*=\s*(\d+)",
                _strip_outer_parens(expr),
                flags=re.I,
            )
            if not m:
                elems = []
                break
            elems.append(int(m.group(1)))
        if elems and all(1 <= e <= 32 for e in elems):
            mask = 0
            for elem in elems:
                mask |= 1 << (elem - 1)
            lo = mask & 0xffff
            hi = (mask >> 16) & 0xffff
            if lo >= 32768:
                lo -= 65536
            if hi >= 32768:
                hi -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_MASK", lo, hi

    if len(triggers) == 1 and len(trigger2) == 1:
        m0 = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        m1 = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)",
            _strip_outer_parens(trigger2[0]),
            flags=re.I,
        )
        if m0 and m1:
            return (
                "IK_CNS_TRIGGER_ANIM_ELEM_EQ_OR",
                int(m0.group(1)),
                int(m1.group(1)),
            )

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])

        m_target = re.fullmatch(
            r"NumTarget(?:\s*\(\s*(-?\d+)\s*\))?"
            r"\s*(=|!=|<=|>=|<|>)\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m_target:
            op = {
                "=": "IK_CNS_QUERY_EQ",
                "!=": "IK_CNS_QUERY_NE",
                "<": "IK_CNS_QUERY_LT",
                "<=": "IK_CNS_QUERY_LE",
                ">": "IK_CNS_QUERY_GT",
                ">=": "IK_CNS_QUERY_GE",
            }[m_target.group(2)]
            return (
                "IK_CNS_TRIGGER_NUM_TARGET_QUERY",
                int(m_target.group(3)),
                op,
            )

        m = re.fullmatch(
            r"(NumProj|ProjContact|ProjHit|ProjGuarded|"
            r"ProjContactTime|ProjHitTime|ProjGuardedTime)"
            r"\s*(=|!=|<=|>=|<|>)\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m:
            field = {
                "numproj": "IK_CNS_PROJ_QUERY_NUM",
                "projcontact": "IK_CNS_PROJ_QUERY_CONTACT",
                "projhit": "IK_CNS_PROJ_QUERY_HIT",
                "projguarded": "IK_CNS_PROJ_QUERY_GUARDED",
                "projcontacttime": "IK_CNS_PROJ_QUERY_CONTACT_TIME",
                "projhittime": "IK_CNS_PROJ_QUERY_HIT_TIME",
                "projguardedtime": "IK_CNS_PROJ_QUERY_GUARDED_TIME",
            }[m.group(1).lower()]
            op = {
                "=": "IK_CNS_QUERY_EQ",
                "!=": "IK_CNS_QUERY_NE",
                "<": "IK_CNS_QUERY_LT",
                "<=": "IK_CNS_QUERY_LE",
                ">": "IK_CNS_QUERY_GT",
                ">=": "IK_CNS_QUERY_GE",
            }[m.group(2)]
            packed_expr = f"(({field}) << 8) | ({op})"
            return (
                "IK_CNS_TRIGGER_PROJECTILE_QUERY",
                int(m.group(3)),
                packed_expr,
            )

        m = re.fullmatch(r"RoundState\s*=\s*(\d+)", value, flags=re.I)
        if m:
            return "IK_CNS_TRIGGER_ROUND_STATE_EQ", int(m.group(1)), 0
        m = re.fullmatch(r"RoundState\s*!=\s*(\d+)", value, flags=re.I)
        if m:
            return "IK_CNS_TRIGGER_ROUND_STATE_NE", int(m.group(1)), 0

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)\s*,\s*>=\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_FROM", int(m.group(1)), 0

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"AnimElem\s*=\s*(\d+)\s*,\s*(-?\d+)",
            value,
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            offset = int(m.group(2))
            if elem < 1 or elem > 255 or offset < -128 or offset > 127:
                raise ValueError(
                    f"[{ctrl.name}] AnimElem offset trigger out of range"
                )
            packed = (elem << 8) | (offset & 0xff)
            if packed >= 32768:
                packed -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED", packed, 0

    if ctype == "afterimagetime" and len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*0",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_FROM", int(m.group(1)), 0
        m = re.fullmatch(
            r"Vel\s+Y\s*<\s*(-?\d+(?:\.\d+)?)",
            value,
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_VY_LT_Q8", q8(float(m.group(1))), 0

        m = re.fullmatch(
            r"AnimTime\s*<\s*(-\d+)",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_ANIM_TIME_REMAIN_GT",
                abs(int(m.group(1))),
                0,
            )

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*(\d+)\s*"
            r"&&\s*Time\s*<\s*(\d+)",
            value,
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            min_time = int(m.group(2))
            state_limit = int(m.group(3))
            if not (1 <= elem <= 255 and 0 <= min_time <= 255):
                raise ValueError(
                    f"[{ctrl.name}] AfterImageTime window out of range"
                )
            packed = (elem << 8) | min_time
            if packed >= 32768:
                packed -= 65536
            return (
                "IK_CNS_TRIGGER_ANIM_ELEM_TIME_GE_STATE_TIME_LT",
                packed,
                state_limit,
            )

    if ctype in ("width", "targetbind", "nothitby") and len(triggers) == 1:
        parsed = _anim_elem_range_trigger(triggers[0])
        if parsed is not None:
            return "IK_CNS_TRIGGER_ANIM_ELEM_RANGE", parsed[0], parsed[1]

    if ctype == "targetbind" and len(triggers) == 1:
        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

    if ctype in ("turn", "posadd", "targetfacing") and len(triggers) == 2:
        normalized = [_strip_outer_parens(t) for t in triggers]
        if any(re.fullmatch(r"var\(\s*2\s*\)", t, flags=re.I)
               for t in normalized):
            elem = next((
                re.fullmatch(r"AnimElem\s*=\s*(\d+)", t, flags=re.I)
                for t in normalized
                if re.fullmatch(r"AnimElem\s*=\s*(\d+)", t, flags=re.I)
            ), None)
            if elem:
                return (
                    "IK_CNS_TRIGGER_STATE_AXIS_FWD_ANIM_ELEM_EQ",
                    int(elem.group(1)), 0,
                )

    if ctype in ("selfstate", "changestate"):
        if ctype == "selfstate" and len(triggers) == 1 and re.fullmatch(
            r"!\s*gethitvar\s*\(\s*isbound\s*\)",
            triggers[0], flags=re.I
        ):
            return "IK_CNS_TRIGGER_NOT_BOUND", 0, 0
        target = integer(ctrl.get("value"), -1)
        trigger_all = ctrl.all("triggerall")
        if target == 5200 and trigger_all:
            return "IK_CNS_TRIGGER_THROW_GROUND_RECOVERY", q8(-20), 0
        if target == 5210 and trigger_all:
            return "IK_CNS_TRIGGER_THROW_AIR_RECOVERY", 0, 0
        normalized = [_strip_outer_parens(t) for t in triggers]
        if ctype == "changestate" and not trigger_all:
            masks = {"holdback": 2, "holddown": 8, "blocking": 128}
            flat = [
                _strip_outer_parens(p)
                for t in normalized
                for p in re.split(r"\s*&&\s*", t)
            ]
            time_eq = [re.fullmatch(r"Time\s*=\s*(\d+)", t, flags=re.I)
                       for t in flat]
            held = [re.fullmatch(r'Command\s*(!?=)\s*"(\w+)"', t, flags=re.I)
                    for t in flat]
            if (len(flat) == 2 and time_eq[0] and held[1] and
                    held[1].group(1) == "=" and
                    held[1].group(2).lower() in ("holdback",)):
                return ("IK_CNS_TRIGGER_TIME_EQ_COMMAND_ACTIVE",
                        int(time_eq[0].group(1)),
                        masks[held[1].group(2).lower()])
            if (flat and all(h and h.group(2).lower() in masks for h in held)
                    and any(h.group(1) == "=" and
                            h.group(2).lower() == "blocking" for h in held)):
                need = 0
                forbid = 0
                for h in held:
                    bit = masks[h.group(2).lower()]
                    if h.group(1) == "=":
                        need |= bit
                    else:
                        forbid |= bit
                return "IK_CNS_TRIGGER_COMMAND_ALL_NONE", need, forbid
        if ctype == "selfstate":
            split = normalized
            if len(normalized) == 1:
                split = [
                    _strip_outer_parens(p)
                    for p in re.split(r"\s*&&\s*", normalized[0])
                ]
            if (len(split) == 2 and
                any(re.fullmatch(r"Vel\s+Y\s*>\s*0", t, flags=re.I)
                    for t in split) and
                any(re.fullmatch(r"Pos\s+Y\s*>=\s*0", t, flags=re.I)
                    for t in split)):
                return "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0

    if ctype == "afterimagetime" and len(triggers) == 1:
        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>=\s*(\d+)\s*&&\s*"
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*(\d+)",
            _strip_outer_parens(triggers[0]), flags=re.I)
        if m:
            a, lo, b, hi = (int(g) for g in m.groups())
            if 1 <= a <= 255 and 1 <= b <= 255 and lo <= 255 and hi <= 255:
                return ("IK_CNS_TRIGGER_ANIM_ELEM_TIME_WINDOW",
                        (a << 8) | lo, (b << 8) | hi)

    if ctype == "width" and len(triggers) == 1:
        parsed = _anim_elem_range_trigger(triggers[0])
        if parsed is not None:
            return "IK_CNS_TRIGGER_ANIM_ELEM_RANGE", parsed[0], parsed[1]

    trigger_all = ctrl.all("triggerall")

    if ctype == "changestate" and len(triggers) in (2, 3):
        normalized = [_strip_outer_parens(t) for t in triggers]
        cmd = next((
            t for t in normalized
            if re.fullmatch(
                r'Command\s*=\s*"a"\s*\|\|\s*Command\s*=\s*"b"',
                t, flags=re.I
            )
        ), None)
        vy = next((
            re.fullmatch(r"Vel\s+y\s*<\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            for t in normalized
            if re.fullmatch(r"Vel\s+y\s*<\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
        ), None)
        time_ok = all(
            re.fullmatch(r"Time\s*>\s*0", t, flags=re.I)
            for t in normalized
            if t != cmd and (not vy or t != vy.group(0))
        )
        if cmd is not None and vy and time_ok:
            return (
                ("IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8_AFTER_ENTRY"
                 if len(normalized) == 3 else "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8"),
                (1 << 5) | (1 << 6),
                q8(float(vy.group(1))),
            )

    if ctype == "changestate" and len(triggers) == 1 and not trigger_all:
        value = _strip_outer_parens(triggers[0])
        parts = [
            _strip_outer_parens(p)
            for p in re.split(r"\s*&&\s*", value)
        ]
        if len(parts) == 2:
            vy = next((
                re.fullmatch(r"Vel\s+Y\s*>\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
                for t in parts
                if re.fullmatch(r"Vel\s+Y\s*>\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            ), None)
            pos = next((
                re.fullmatch(r"Pos\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
                for t in parts
                if re.fullmatch(r"Pos\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)", t, flags=re.I)
            ), None)
            if vy and pos:
                return (
                    "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL",
                    q8(float(pos.group(1))),
                    q8(float(vy.group(1))),
                )

    if ctype in ("changestate", "screenbound") and len(trigger_all) == 1 \
       and len(triggers) == 1 and len(trigger2) == 1:
        y = re.fullmatch(
            r"Pos\s+y\s*<\s*(-?\d+)",
            _strip_outer_parens(trigger_all[0]),
            flags=re.I,
        )
        back = re.fullmatch(
            r"BackEdgeBodyDist\s*(<=|<)\s*(\d+)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        front = re.fullmatch(
            r"FrontEdgeBodyDist\s*(<=|<)\s*(\d+)",
            _strip_outer_parens(trigger2[0]),
            flags=re.I,
        )
        if y and back and front and back.groups() == front.groups():
            return (
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE" +
                ("_LT" if back.group(1) == "<" else ""),
                q8(float(y.group(1))),
                int(back.group(2)),
            )

    if ctype == "turn" and len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        m = re.fullmatch(
            r"\(?\s*Time\s*=\s*0\s*\)?\s*&&\s*"
            r"\(?\s*FrontEdgeBodyDist\s*<=\s*(\d+)\s*\)?",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE",
                int(m.group(1)), 0,
            )
        m = re.fullmatch(
            r"\(?\s*Time\s*=\s*0\s*\)?\s*&&\s*"
            r"\(?\s*BackEdgeDist\s*<\s*(\d+)\s*\)?",
            value,
            flags=re.I,
        )
        if m:
            return (
                "IK_CNS_TRIGGER_STATE_ENTRY_BACK_EDGE_LT",
                int(m.group(1)), 0,
            )

    if len(triggers) == 1:
        value = _strip_outer_parens(triggers[0])
        if re.fullmatch(r"MoveHit", value, flags=re.I):
            return "IK_CNS_TRIGGER_MOVE_HIT", 0, 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*=\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            elem = int(m.group(1))
            first = int(m.group(2))
            last = int(m.group(3))
            if not (1 <= elem <= 32767 and -128 <= first <= 127 and -128 <= last <= 127):
                raise ValueError(
                    f"[{ctrl.name}] AnimElemTime range trigger out of range"
                )
            packed = ((first & 0xff) << 8) | (last & 0xff)
            if packed >= 32768:
                packed -= 65536
            return "IK_CNS_TRIGGER_ANIM_ELEM_TIME_RANGE", elem, packed

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*<\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_BEFORE", int(m.group(1)), 0

        m = re.fullmatch(
            r"AnimElemTime\s*\(\s*(\d+)\s*\)\s*>\s*0",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_ANIM_ELEM_AFTER", int(m.group(1)), 0

        m = re.fullmatch(
            r"Vel\s+Y\s*>=\s*(-?\d+(?:\.\d+)?)",
            _strip_outer_parens(triggers[0]),
            flags=re.I,
        )
        if m:
            return "IK_CNS_TRIGGER_VY_GE_Q8", q8(float(m.group(1))), 0

    if len(triggers) == 1 and re.fullmatch(
        r"HitShakeOver\s*=\s*1",
        _strip_outer_parens(triggers[0]),
        flags=re.I,
    ):
        return "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0

    if ctype == "changeanim":
        parsed = _move_contact_window(triggers)
        if parsed is not None:
            return (
                "IK_CNS_TRIGGER_MOVE_CONTACT_ELEM_WINDOW",
                parsed[0],
                parsed[1],
            )

    return simple_trigger(ctrl)

