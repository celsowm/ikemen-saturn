#!/usr/bin/env python3
"""Source-attributed first-state-divergence window for Ikemen GO vs Saturn.

This is an observation report, not a claim that an observed random predicate
evaluated to true or that the CPU/global RNG streams can be aligned.
"""
from __future__ import annotations

from collections import defaultdict

RANGE_BEFORE = 2
RANGE_AFTER = 2


def _root(row: dict, player: int) -> dict:
    matching = [
        c for c in row.get("chars", [])
        if c.get("player_no") == player and c.get("helper_index") == 0
    ]
    if len(matching) != 1:
        raise ValueError("first divergence requires exactly one root per player")
    return matching[0]


def first_divergence_window(
    upstream: list[dict],
    native: list[dict],
    player: int,
    rng_events: list[dict] | None = None,
    *,
    before: int = RANGE_BEFORE,
    after: int = RANGE_AFTER,
) -> dict:
    """Describe the first state mismatch and surrounding recorded RNG calls.

    GO events must have already been validated by rng_events.audit_events
    before passing them to this routine. We verify frame bounds and order
    regardless, and never treat event provenance as a selected move.
    """
    if not upstream or len(upstream) != len(native):
        raise ValueError("both aligned nonempty traces are required")
    if type(player) is not int or player not in (0, 1):
        raise ValueError("player must be 0 or 1")
    if (type(before) is not int or type(after) is not int or
        before < 0 or after < 0 or before > 60 or after > 60):
        raise ValueError("invalid divergence window bounds")
    for i, (up, sat) in enumerate(zip(upstream, native)):
        if up.get("frame") != sat.get("frame") or up.get("frame") != i:
            raise ValueError(f"misaligned frame index at {i}")
    mismatch = next(
        (i for i, (up, sat) in enumerate(zip(upstream, native))
         if _root(up, player)["state_no"] != _root(sat, player)["state_no"]),
        None,
    )
    if mismatch is None:
        return {"available": False, "reason": "states match in all frames"}

    lo, hi = max(0, mismatch - before), min(len(upstream), mismatch + after + 1)
    calls: dict[int, list[dict]] = defaultdict(list)
    if rng_events is not None:
        last_frame = -1
        for event in rng_events:
            frame = event.get("frame")
            if type(frame) is not int or frame < last_frame or not 0 <= frame < len(upstream):
                raise ValueError("unordered or out-of-range GO RNG event")
            last_frame = frame
            if lo <= frame < hi:
                calls[frame].append(event)

    context: list[dict] = []
    for i in range(lo, hi):
        u, s = upstream[i], native[i]
        x, y = _root(u, player), _root(s, player)
        original_calls = calls[i]
        ai_calls = [
            e for e in original_calls
            if (e.get("expr_resolution") == "unique" and
                e.get("player_no") == player and
                str(e.get("expr_file", "")).lower().endswith("/ai.zss"))
        ]
        def character(c: dict) -> dict:
            return {
                "state": c["state_no"], "state_time": c["state_time"],
                "move_type": c.get("move_type"), "ctrl": c.get("ctrl"),
                "pos": c.get("pos"), "facing": c.get("facing"),
            }
        context.append({
            "frame": i,
            "states_equal": x["state_no"] == y["state_no"],
            "go_cpu": character(x),
            "saturn_cpu": character(y),
            "go_opponent": character(_root(u, player ^ 1)),
            "saturn_opponent": character(_root(s, player ^ 1)),
            "go_global_rng_post_frame": u.get("rand_seed"),
            "native_local_rng_post_frame": (
                s.get("native_ai_rng", [None, None])[player]),
            "go_total_random_calls": len(original_calls) if rng_events is not None else None,
            "go_ai_zss_random_calls": len(ai_calls) if rng_events is not None else None,
            "go_ai_zss_predicates_evaluated": [
                {
                    "source": str(e["expr_file"]),
                    "end_line": e["expr_end_line"],
                    "expression": str(e["expr_text"])[:180],
                    "random_0_999": e["value"] // 2147484,
                }
                for e in ai_calls[:16]
            ],
            "go_ai_events_truncated": max(0, len(ai_calls) - 16),
        })
    return {
        "available": True,
        "first_mismatch_frame": mismatch,
        "window_start": lo,
        "window_end_exclusive": hi,
        "has_attributed_go_events": rng_events is not None,
        "note": "Observed GO bytecode expressions are evaluations, not "
                "confirmed transitions; the GO RNG is engine-global, "
                "Saturn RNG is CPU-local. No cause or parity inferred.",
        "frames": context,
    }
