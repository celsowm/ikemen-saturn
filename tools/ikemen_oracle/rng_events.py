#!/usr/bin/env python3
"""Check and summarize original GO Random() call-site events.

Events are written by the opt-in oracle hook after each Random() update.
The first frame cannot be replayed without a pre-frame seed. Subsequent
frames *must* match both consecutive Park-Miller outputs and the post-frame
global seed. No event is interpreted as an AI decision by itself.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

try:
    from .rng_audit import next_seed
    from .diff import load_jsonl
except ImportError:
    from rng_audit import next_seed
    from diff import load_jsonl


def audit_events(frames: list[dict], events: list[dict]) -> dict:
    if not frames:
        raise ValueError("empty GO frame trace")
    counts = [0] * len(frames)
    files: Counter[str] = Counter()
    contexts: Counter[str] = Counter()
    expression_status: Counter[str] = Counter()
    unique_expressions: Counter[str] = Counter()
    original_ai_expressions: Counter[str] = Counter()
    previous_frame = -1
    previous_ordinal = 0
    per_frame: list[list[dict]] = [[] for _ in frames]
    for event in events:
        frame = event.get("frame")
        ordinal = event.get("ordinal")
        value = event.get("value")
        if type(frame) is not int or frame < previous_frame or frame < 0 or frame >= len(frames):
            raise ValueError("RNG event frame order/range invalid")
        if type(ordinal) is not int or ordinal != previous_ordinal + 1:
            raise ValueError("RNG event ordinals must be contiguous and monotonic")
        if type(value) is not int or not 1 <= value <= 2147483646:
            raise ValueError("invalid Random() result in event")
        file = event.get("file")
        function = event.get("function")
        if not isinstance(file, str) or not file or not isinstance(function, str):
            raise ValueError("RNG event is missing call-site provenance")
        player = event.get("player_no")
        state = event.get("state_no")
        if type(player) is not int or not -1 <= player <= 1:
            raise ValueError("RNG event is missing player attribution")
        if type(state) is not int:
            raise ValueError("RNG event is missing state attribution")
        resolution = event.get("expr_resolution")
        if resolution not in ("unique", "ambiguous", "unresolved"):
            raise ValueError("RNG event has invalid expression resolution")
        if resolution == "unique":
            expr_file = event.get("expr_file")
            expr_end_line = event.get("expr_end_line")
            expr_text = event.get("expr_text")
            if (not isinstance(expr_file, str) or not expr_file or
                type(expr_end_line) is not int or expr_end_line <= 0 or
                not isinstance(expr_text, str) or not expr_text):
                raise ValueError("uniquely resolved expression lacks original source")
            unique_expressions[f"{expr_file}:{expr_end_line}: {expr_text[:90]}"] += 1
            if Path(expr_file).name.casefold() == "ai.zss":
                original_ai_expressions[f"{expr_file}:{expr_end_line}: {expr_text[:110]}"] += 1
        previous_frame, previous_ordinal = frame, ordinal
        counts[frame] += 1
        files[file] += 1
        expression_status[resolution] += 1
        contexts[f"p{player + 1 if player >= 0 else 'global'}:{state}"] += 1
        per_frame[frame].append(event)

    # The first capture has no saved preceding seed. All later active
    # intervals must reconcile the exact Random() sequence to the saved
    # global state. This catches missed calls and RNG resets.
    for i in range(1, len(frames)):
        seed = frames[i - 1].get("rand_seed")
        if type(seed) is not int or not 1 <= seed <= 2147483646:
            raise ValueError(f"invalid GO frame checkpoint at {i - 1}")
        for event in per_frame[i]:
            seed = next_seed(seed)
            if seed != event["value"]:
                raise ValueError(f"GO Random() value mismatch at frame {i}, ordinal {event['ordinal']}")
        if seed != frames[i].get("rand_seed"):
            raise ValueError(f"GO RNG event count/state mismatch at frame {i}")
    if per_frame[0] and per_frame[0][-1]["value"] != frames[0].get("rand_seed"):
        raise ValueError("first-frame RNG events disagree with checkpoint")

    return {
        "schema": 1,
        "scope": "GO engine-global random calls with optional bytecode owner",
        "frame_count": len(frames),
        "event_count": len(events),
        "counts_by_frame": counts,
        "verified_intervals": max(0, len(frames) - 1),
        "unverified_first_frame": True,
        "by_file": dict(files.most_common()),
        "by_player_state": dict(contexts.most_common()),
        "expression_resolution": dict(expression_status.most_common()),
        "unique_source_expressions": dict(unique_expressions.most_common(25)),
        "original_ai_zss_expressions": dict(original_ai_expressions.most_common(30)),
        "original_ai_zss_resolved_draws": sum(original_ai_expressions.values()),
        "uniquely_resolved_calls": expression_status["unique"],
        "unresolved_or_ambiguous_calls": expression_status["unresolved"] + expression_status["ambiguous"],
        "first_16_events": events[:16],
        "first_12_bytecode_events": [
            event for event in events if event["file"] == "bytecode.go"
        ][:12],
        "first_12_cpu_events": [
            event for event in events if event["player_no"] >= 0
        ][:12],
        "first_12_unique_expressions": [
            event for event in events if event["expr_resolution"] == "unique"
        ][:12],
        "first_12_ai_zss_random_draws": [
            event for event in events
            if (event["expr_resolution"] == "unique" and
                Path(event["expr_file"]).name.casefold() == "ai.zss")
        ][:12],
        "all_saved_intervals_reconciled": True,
        "ai_decision_parity_verified": False,
    }


def load_and_audit(frames: list[dict], path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"no upstream RNG call-site sidecar: {path}")
    return audit_events(frames, load_jsonl(path))
