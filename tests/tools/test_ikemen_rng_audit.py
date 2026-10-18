#!/usr/bin/env python3
"""Bounded Park-Miller draw audit tests, independent of SDL and LibSaturn."""
from tools.ikemen_oracle.rng_audit import (
    MAX_FRAME_DRAWS, MODULUS, audit_checkpoints, compare_draws,
    draws_between, next_seed,
)

assert next_seed(1) == 16807
assert next_seed(16807) == 282475249
assert next_seed(282475249) == 1622650073
assert next_seed(1622650073) == 984943658
assert next_seed(2147483646) == 2147466840
assert draws_between(1, 1) == 0
assert draws_between(1, 16807) == 1
assert draws_between(1, 282475249) == 2
assert draws_between(16807, 984943658) == 3
assert draws_between(1, 282475249, limit=1) is None
assert draws_between(1, 282475249, limit=2) == 2

go = audit_checkpoints([1, 16807, 282475249, 984943658], limit=8)
cpu = audit_checkpoints([1, 282475249, 1622650073, 984943658], limit=8)
assert go["draws_by_frame"] == [None, 1, 1, 2]
assert cpu["draws_by_frame"] == [None, 2, 1, 1]
assert go["resolved_intervals"] == 3
assert go["observed_draws_in_resolved_intervals"] == 4
assert go["unresolved_frames"] == []
cmp = compare_draws(go, cpu)
assert cmp["available"]
assert cmp["different_draw_count_frames"] == 2
assert cmp["first_different_draw_count"] == {
    "frame": 1, "go_global_draws": 1, "native_cpu_draws": 2
}
assert compare_draws(None, cpu)["available"] is False
assert audit_checkpoints([1, 984943658], limit=1)["unresolved_frames"] == [1]
assert MAX_FRAME_DRAWS >= 1000

for sample in (0, -1, MODULUS, 1.0, "1", True):
    try:
        next_seed(sample)
    except ValueError:
        pass
    else:
        raise AssertionError(f"invalid Park-Miller seed accepted: {sample!r}")
for bad in (-1, 1.5, True, 1_000_001):
    try:
        draws_between(1, 16807, limit=bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"invalid draw search limit accepted: {bad!r}")
try:
    audit_checkpoints([])
except ValueError:
    pass
else:
    raise AssertionError("empty RNG history accepted")
try:
    compare_draws(go, audit_checkpoints([1, 16807]))
except ValueError:
    pass
else:
    raise AssertionError("misaligned RNG histories accepted")
print("GO Park-Miller post-frame draw-count audit: OK")
