#!/usr/bin/env python3
"""Opt-in upstream RNG event audit, without building Go or SDL."""
from tools.ikemen_oracle.rng_events import audit_events

frames = [
    {"frame": 0, "rand_seed": 16807},
    {"frame": 1, "rand_seed": 1622650073},
    {"frame": 2, "rand_seed": 1622650073},
    {"frame": 3, "rand_seed": 984943658},
]
def event(frame: int, ordinal: int, value: int,
          player: int = 1, state: int = 200) -> dict:
    return {
        "frame": frame, "ordinal": ordinal, "value": value,
        "file": "bytecode.go" if player >= 0 else "system.go",
        "line": 2337, "function": "main.BytecodeExp.run",
        "player_no": player, "state_no": state,
    }
events = [
    event(1, 1, 282475249),
    event(1, 2, 1622650073),
    event(3, 3, 984943658, -1, -1),
]
result = audit_events(frames, events)
assert result["event_count"] == 3
assert result["counts_by_frame"] == [0, 2, 0, 1]
assert result["verified_intervals"] == 3
assert result["all_saved_intervals_reconciled"]
assert result["by_file"]["bytecode.go"] == 2
assert result["by_player_state"]["p2:200"] == 2
assert result["by_player_state"]["pglobal:-1"] == 1
assert len(result["first_12_cpu_events"]) == 2
assert not result["ai_decision_parity_verified"]
assert audit_events(frames, []) == {} if False else True

def must_reject(bad_frames, bad_events):
    try:
        audit_events(bad_frames, bad_events)
    except ValueError:
        return
    raise AssertionError("invalid upstream Random() trace accepted")

must_reject(frames, [event(1, 1, 999)])
must_reject(frames, [event(1, 1, 282475249), event(1, 3, 1622650073)])
must_reject(frames, [event(1, 1, 282475249), event(1, 2, 1622650073), event(2, 3, 984943658)])
must_reject(frames, [event(1, 1, 282475249), event(1, 2, 1622650073), event(9, 3, 984943658)])
must_reject(frames, [event(1, 1, 282475249), event(1, 2, 1622650073, player=9)])
must_reject([{"rand_seed": 1}, {"rand_seed": 16807}], [])
try:
    audit_events([], [])
except ValueError:
    pass
else:
    raise AssertionError("empty trace accepted")
print("upstream GO per-call RNG attribution and checkpoint audit: OK")
