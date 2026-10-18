#!/usr/bin/env python3
"""CPU diagnostics and CLI contract tests do not require upstream Go or SDL."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from tools.ikemen_oracle.run_saturn import cpu_levels, build_trace_command
from tools.ikemen_oracle.ai_compare import compare_ai


SCENARIO = {
    "name": "cpu_fixture", "frames": 3, "seed": 23,
    "p1": "../chars/kfm/kfm.def",
    "p2": "../chars/kfm_zss/kfm_zss.def",
    "p1_ai": 0, "p2_ai": 8,
}
assert cpu_levels(SCENARIO) == (0, 8)
with TemporaryDirectory() as d:
    base = Path(d)
    cmd = build_trace_command(base / "bin", base / "out.jsonl",
                              SCENARIO, base / "inputs.txt")
    assert cmd[-4:] == ["kfm", "kfm_zss", "0", "8"]
    script = dict(SCENARIO, p2_ai=0)
    assert len(build_trace_command(base / "bin", base / "out.jsonl",
                                   script, base / "inputs.txt")) == 8
    for key, val in (("p2_ai", -1), ("p2_ai", 9),
                     ("p2_ai", 3.0), ("p2_ai", True)):
        changed = dict(SCENARIO, **{key: val})
        try:
            cpu_levels(changed)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted unsupported CPU level: {val}")
    try:
        cpu_levels(dict(SCENARIO, p2="../chars/kfm/kfm.def"))
    except ValueError as e:
        assert "only supports KFM ZSS" in str(e)
    else:
        raise AssertionError("silent classic KFM AI fallback accepted")


def trace_row(frame: int, state: int, move_type: int) -> dict:
    return {
        "schema": 1, "frame": frame,
        "chars": [{
            "player_no": 1, "helper_index": 0, "state_no": state,
            "state_time": frame if state == 0 else 0,
            "move_type": move_type,
        }],
    }


up = [trace_row(0, 0, 0), trace_row(1, 200, 1), trace_row(2, 200, 1)]
native = [trace_row(0, 0, 0), trace_row(1, 100, 0), trace_row(2, 200, 1)]
report = compare_ai(up, native, 1)
assert report["frames"] == 3
assert report["state_equal_frames"] == 2
assert report["state_mismatch_frames"] == 1
assert report["first_state_mismatch"]["frame"] == 1
assert report["upstream_attack_frames"] == 2
assert report["saturn_attack_frames"] == 1
assert report["observed_attacks_on_both_sides"]
assert report["ai_parity_verified"] is False
assert report["random_debug"]["native_cpu_first"] is None
assert report["random_debug"]["same_random_stream"] is False
for i, row in enumerate(native):
    row["native_ai_rng"] = [None, (i + 1) * 16807]
up[0]["rand_seed"] = 1
up[-1]["rand_seed"] = 77
snapshots = compare_ai(up, native, 1)
assert snapshots["random_debug"]["native_cpu_first"] == 16807
assert snapshots["random_debug"]["native_cpu_last"] == 50421
assert snapshots["random_debug"]["upstream_global_last"] == 77
native[1].pop("native_ai_rng")
try:
    compare_ai(up, native, 1)
except ValueError:
    pass
else:
    raise AssertionError("incomplete native random trace accepted")
native[1]["native_ai_rng"] = [None, 33614]
assert report["upstream"]["state_histogram"]["200"] == 2
for a, b in ((up, []), (up, native[:2])):
    try:
        compare_ai(a, b, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated AI trace accepted")
bad = [trace_row(0, 0, 0), trace_row(9, 100, 0), trace_row(2, 200, 1)]
try:
    compare_ai(up, bad, 1)
except ValueError as exc:
    assert "indices differ" in str(exc)
else:
    raise AssertionError("misaligned AI trace accepted")
print("native/upstream AI CLI and comparison diagnostics OK")
