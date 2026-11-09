"""Compile CNS attack, guard, reversal, and hit attribute masks."""
from __future__ import annotations

import re


def attack_attr_mask(text: str | None) -> str:
    value = (text or "").strip().upper()
    mapping = {
        "NA": "IK_CNS_ATTR_NORMAL_ATTACK",
        "SA": "IK_CNS_ATTR_SPECIAL_ATTACK",
        "HA": "IK_CNS_ATTR_HYPER_ATTACK",
        "NP": "IK_CNS_ATTR_NORMAL_PROJECTILE",
        "SP": "IK_CNS_ATTR_SPECIAL_PROJECTILE",
        "HP": "IK_CNS_ATTR_HYPER_PROJECTILE",
        "NT": "IK_CNS_ATTR_NORMAL_THROW",
        "ST": "IK_CNS_ATTR_SPECIAL_THROW",
        "HT": "IK_CNS_ATTR_HYPER_THROW",
    }
    if value == "AP":
        return (
            "IK_CNS_ATTR_NORMAL_PROJECTILE | "
            "IK_CNS_ATTR_SPECIAL_PROJECTILE | "
            "IK_CNS_ATTR_HYPER_PROJECTILE"
        )
    if value == "AA":
        return (
            "IK_CNS_ATTR_NORMAL_ATTACK | "
            "IK_CNS_ATTR_SPECIAL_ATTACK | "
            "IK_CNS_ATTR_HYPER_ATTACK"
        )
    if value == "AT":
        return (
            "IK_CNS_ATTR_NORMAL_THROW | "
            "IK_CNS_ATTR_SPECIAL_THROW | "
            "IK_CNS_ATTR_HYPER_THROW"
        )
    bits = [mapping[token] for token in re.split(r"\s+", value) if token in mapping]
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def attack_state_mask(text: str | None) -> int:
    value = (text or "SCA").strip().upper()
    mask = 0
    if "S" in value:
        mask |= 1
    if "C" in value:
        mask |= 2
    if "A" in value:
        mask |= 4
    return mask or 7


def priority_type_code(text: str | None) -> str:
    value = (text or "4, Hit").split(",", 1)
    kind = value[1].strip().lower() if len(value) > 1 else "hit"
    if kind in ("miss", "m"):
        return "IK_CNS_PRIORITY_MISS"
    if kind in ("dodge", "d"):
        return "IK_CNS_PRIORITY_DODGE"
    return "IK_CNS_PRIORITY_HIT"


def guard_mask(text: str | None) -> str:
    value = (text or "").strip().upper()
    bits: list[str] = []
    if "H" in value:
        bits.append("IK_CNS_GUARD_STAND")
    if "L" in value:
        bits.append("IK_CNS_GUARD_CROUCH")
    if "M" in value:
        bits += ["IK_CNS_GUARD_STAND", "IK_CNS_GUARD_CROUCH"]
    if "A" in value:
        bits.append("IK_CNS_GUARD_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def no_hit_by_state_mask(text: str | None) -> str:
    value = (text or "").split(",", 1)[0].strip().upper()
    if value == "":
        return "0u"
    bits: list[str] = []
    if "S" in value:
        bits.append("IK_CNS_REVERSAL_STATE_STAND")
    if "C" in value:
        bits.append("IK_CNS_REVERSAL_STATE_CROUCH")
    if "A" in value:
        bits.append("IK_CNS_REVERSAL_STATE_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def hit_by_state_mask(text: str | None) -> str:
    """Compile the optional S/C/A attacker-state portion of HitBy.value."""
    return no_hit_by_state_mask(text)


def no_hit_by_attr_mask(text: str | None) -> str:
    parts = [part.strip().upper() for part in (text or "").split(",")]
    if len(parts) <= 1:
        return "0u"
    bits: list[str] = []
    for token in parts[1:]:
        if token == "AT":
            bits.extend([
                "IK_CNS_ATTR_NORMAL_THROW",
                "IK_CNS_ATTR_SPECIAL_THROW",
                "IK_CNS_ATTR_HYPER_THROW",
            ])
            continue
        mask = attack_attr_mask(token)
        if mask != "0u":
            bits.extend(part.strip() for part in mask.split("|"))
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def reversal_state_mask(text: str | None) -> str:
    """Compile the state-type half of ReversalDef.attr."""
    value = (text or "").strip().upper()
    bits: list[str] = []
    if "S" in value:
        bits.append("IK_CNS_REVERSAL_STATE_STAND")
    if "C" in value:
        bits.append("IK_CNS_REVERSAL_STATE_CROUCH")
    if "A" in value:
        bits.append("IK_CNS_REVERSAL_STATE_AIR")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"


def hit_mask(text: str | None) -> str:
    value = (text or "MAF").strip().upper()
    bits: list[str] = []
    if "H" in value:
        bits.append("IK_CNS_HIT_STAND")
    if "L" in value:
        bits.append("IK_CNS_HIT_CROUCH")
    if "M" in value:
        bits += ["IK_CNS_HIT_STAND", "IK_CNS_HIT_CROUCH"]
    if "A" in value:
        bits.append("IK_CNS_HIT_AIR")
    if "F" in value:
        bits.append("IK_CNS_HIT_FALL")
    if "D" in value:
        bits.append("IK_CNS_HIT_DOWN")
    if "+" in value:
        bits.append("IK_CNS_HIT_ONLY_GETHIT")
    if "-" in value:
        bits.append("IK_CNS_HIT_NOT_GETHIT")
    return " | ".join(dict.fromkeys(bits)) if bits else "0u"
