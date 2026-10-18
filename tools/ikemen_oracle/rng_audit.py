#!/usr/bin/env python3
"""Bounded audit of Park-Miller Random() calls between saved game frames.

The pinned Ikemen GO uses multiplicative Park-Miller, modulus 2147483647
and multiplier 16807. For seeds in the positive normal cycle, iterating
the recurrence allows a *bounded* count of random draws between two
consecutive post-frame snapshots WITHOUT patching the Go engine.

Counts apply to the entire upstream game (not just its KFM ZSS AI).
Native AI uses an independent, per-player stream. No positional/game
parity is implied by coincident counts.
"""
from __future__ import annotations

MODULUS = 2147483647
MULTIPLIER = 16807
MAX_FRAME_DRAWS = 4096


def _require_seed(seed: int) -> int:
    if type(seed) is not int or not 1 <= seed < MODULUS:
        raise ValueError(
            "RNG checkpoint must be a positive Park-Miller state "
            "in [1, 2147483646]"
        )
    return seed


def next_seed(seed: int) -> int:
    """Mathematically equivalent to pinned Go Random() for normal seeds."""
    return (_require_seed(seed) * MULTIPLIER) % MODULUS


def draws_between(before: int, after: int, *,
                  limit: int = MAX_FRAME_DRAWS) -> int | None:
    """Find draws in [0, limit], or None if not reached.

    With a bounded search, count=0 means no calls in this window; callers
    must not interpret it as a general proof against a full-period wrap.
    """
    _require_seed(before)
    _require_seed(after)
    if type(limit) is not int or limit < 0 or limit > 1_000_000:
        raise ValueError("limit must be an integer in [0, 1000000]")
    if before == after:
        return 0
    value = before
    for draws in range(1, limit + 1):
        value = (value * MULTIPLIER) % MODULUS
        if value == after:
            return draws
    return None


def audit_checkpoints(checkpoints: list[int], *,
                      limit: int = MAX_FRAME_DRAWS) -> dict:
    """Return frame-aligned counts. Frame 0 has no prior post-frame seed."""
    if not checkpoints:
        raise ValueError("empty random checkpoint series")
    for seed in checkpoints:
        _require_seed(seed)
    if type(limit) is not int or limit < 0 or limit > 1_000_000:
        raise ValueError("invalid random draw search bound")
    counts: list[int | None] = [None]
    unresolved: list[int] = []
    for i in range(1, len(checkpoints)):
        count = draws_between(checkpoints[i - 1], checkpoints[i],
                              limit=limit)
        counts.append(count)
        if count is None:
            unresolved.append(i)
    resolved = [n for n in counts[1:] if n is not None]
    return {
        "available": True,
        "post_frame_first_seed": checkpoints[0],
        "post_frame_last_seed": checkpoints[-1],
        "draws_by_frame": counts,
        "max_draws_searched_per_frame": limit,
        "resolved_intervals": len(resolved),
        "unresolved_frames": unresolved,
        "observed_draws_in_resolved_intervals": sum(resolved),
        "frames_without_prior_checkpoint": [0],
    }


def compare_draws(original: dict | None, native: dict | None) -> dict:
    """Compare *counts*, explicitly not the unrelated raw RNG states."""
    if original is None or native is None:
        return {
            "available": False,
            "reason": "both original global and native CPU post-frame "
                      "checkpoints are required",
        }
    if len(original["draws_by_frame"]) != len(native["draws_by_frame"]):
        raise ValueError("RNG trace frame counts differ")
    mismatches = []
    for i, (go, cpu) in enumerate(zip(original["draws_by_frame"][1:],
                                       native["draws_by_frame"][1:]), 1):
        if go is not None and cpu is not None and go != cpu:
            mismatches.append({
                "frame": i,
                "go_global_draws": go,
                "native_cpu_draws": cpu,
            })
    return {
        "available": True,
        "first_different_draw_count": mismatches[0] if mismatches else None,
        "different_draw_count_frames": len(mismatches),
        "first_12_differences": mismatches[:12],
        "note": "Go counts include all engine systems; Saturn counts only "
                "native ZSS AI. Equal counts do not demonstrate AI parity.",
    }
