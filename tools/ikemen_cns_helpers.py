"""Compile CNS helpers controller records."""
from __future__ import annotations

try:
    from .ikemen_cns_parse import Section
except ImportError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_cns_parse import Section


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
    character_name_hash = services['character_name_hash']
    supported_keys = {
        "type", "helpertype", "postype", "ownpal", "stateno", "name",
        "keyctrl", "id", "pos", "facing", "ignorehitpause",
        "pausemovetime", "pausemove", "supermove", "supermovetime",
        "persistent", "sprpriority",
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
        "front": "IK_CNS_HELPER_POS_FRONT",
        "back": "IK_CNS_HELPER_POS_BACK",
        "left": "IK_CNS_HELPER_POS_LEFT",
        "right": "IK_CNS_HELPER_POS_RIGHT",
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
    if ctrl.get("supermovetime") is not None:
        super_move_time = integer(ctrl.get("supermovetime"), 0)
    else:
        super_move_time = (
            0xFFFFFFFF if integer(ctrl.get("supermove"), 0) else 0
        )

    helper = {
        "id": integer(ctrl.get("id"), 0),
        "state_no": integer(ctrl.get("stateno"), 0),
        # Helper positions are stored as int32 Q8 in the runtime. Use the
        # matching range here; the 16-bit default rejects valid offsets such
        # as Kyo's screen-edge helper at (160, 120).
        "pos_x_q8": q8(px, wide=True),
        "pos_y_q8": q8(py, wide=True),
        "name_hash": character_name_hash(
            (ctrl.get("name") or "").strip().strip('"'))
            if ctrl.get("name") else 0,
        "facing": facing,
        "spr_priority": max(-127, min(127, integer(
            ctrl.get("sprpriority"), 0))),
        "postype": postype,
        # MUGEN booleans commonly use 99999 for true. These fields are
        # represented as uint8_t flags in the runtime, so preserve truth
        # semantics instead of truncating the source integer (99999 -> 159).
        "keyctrl": int(integer(ctrl.get("keyctrl"), 0) != 0),
        "ownpal": int(integer(ctrl.get("ownpal"), 0) != 0),
        "pause_move_time": min(0xFFFFFFFF, max(0, integer(
            ctrl.get("pausemovetime", ctrl.get("pausemove")), 0))),
        "super_move_time": min(0xFFFFFFFF, max(0, super_move_time)),
    }
    controller = {
        "state_number": state_no,
        "type": "IK_CNS_CTRL_HELPER",
        "trigger_kind": trig_kind,
        "trigger_value": trig_value,
        "trigger_value2": trig_value2,
        "value0": helper_index,
        "value1": 1 if integer(ctrl.get("persistent"), 1) == 0 else 0,
        "flags": (
            "IK_CNS_CTRL_IGNORE_HIT_PAUSE"
            if integer(ctrl.get("ignorehitpause"), 0)
            else "0u"
        ),
    }
    return controller, helper
