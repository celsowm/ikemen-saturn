#!/usr/bin/env python3
"""Regression for the first state divergence explanation."""
from tools.ikemen_oracle.first_divergence import first_divergence_window as report


def sample(i, state, opponent=0, seed=1):
    return {
        "frame": i, "rand_seed": seed, "native_ai_rng": [None, seed],
        "chars": [
            {"player_no": 0, "helper_index": 0, "state_no": opponent,
             "state_time": i, "move_type": 0, "ctrl": True,
             "pos": [-30, 0, 0], "facing": 1},
            {"player_no": 1, "helper_index": 0, "state_no": state,
             "state_time": i, "move_type": 0, "ctrl": True,
             "pos": [30, 0, 0], "facing": -1},
        ],
    }


def random_event(frame, ordinal, expression, value=16807):
    return {
        "frame": frame, "ordinal": ordinal, "value": value,
        "player_no": 1, "expr_resolution": "unique",
        "expr_file": "../Ikemen-GO-Screenpack/chars/kfm_zss/AI.zss",
        "expr_end_line": 231, "expr_text": expression,
    }


go = [sample(0, 20), sample(1, 20), sample(2, 210), sample(3, 210)]
sat = [sample(0, 20), sample(1, 20), sample(2, 440), sample(3, 440)]
events = [random_event(1, 1, "random < 249"),
          random_event(2, 2, "random < 250", 282475249)]
r = report(go, sat, 1, events)
assert r["first_mismatch_frame"] == 2
assert r["window_start"] == 0
assert r["window_end_exclusive"] == 4
assert r["has_attributed_go_events"]
assert r["frames"][2]["go_cpu"]["state"] == 210
assert r["frames"][2]["saturn_cpu"]["state"] == 440
assert r["frames"][2]["go_ai_zss_random_calls"] == 1
assert r["frames"][2]["go_ai_zss_predicates_evaluated"][0]["end_line"] == 231
assert r["frames"][2]["go_ai_zss_predicates_evaluated"][0]["random_0_999"] == 131
assert not r["frames"][1]["go_ai_events_truncated"]
assert report(go, sat, 1)["frames"][2]["go_total_random_calls"] is None
assert not report(go, go, 1)["available"]
assert report(go, sat, 1, events, before=0, after=0)["window_start"] == 2
for bad_go, bad_sat, bad_events, opts in [
    ([], [], None, {}),
    (go, sat[:1], None, {}),
    ([sample(9, 20)] + go[1:], sat, None, {}),
    (go, sat, list(reversed(events)), {}),
    (go, sat, None, {"before": -1}),
    (go, sat, None, {"after": True}),
]:
    try:
        report(bad_go, bad_sat, 1, bad_events, **opts)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed divergence input accepted")
print("first CPU state divergence and attributed Go RNG window: OK")
