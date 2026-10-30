#!/usr/bin/env python3
"""ZSS state coverage: numbers must match the pinned source and lowering."""
from __future__ import annotations

from pathlib import Path

from tools.ikemen_zss_character_states import CHARACTER_STATES, HIT_STATES
from tools.ikemen_zss_state_coverage import FILES, inventory

native = set(CHARACTER_STATES) | set(HIT_STATES)
assert len(CHARACTER_STATES) == 40, "kfm.zss native set changed"
assert len(HIT_STATES) == 6, "hits.zss native set changed"

# The pinned lowering source (cmake/IkemenAssets.cmake), not the newer
# 3-axis chars/kfm_zaxis development copy.
char_dir = Path(".external/Ikemen-GO-Screenpack/chars/kfm_zss")
for name in FILES:
    assert (char_dir / name).is_file(), \
        "run scripts/fetch_external.py for the pinned ZSS sources"

rows = inventory(char_dir)
statedefs = set(rows["sources"])
native_numbers = set(rows["native"])
remaining = set(rows["remaining"])
assert native_numbers == statedefs & native
assert remaining == statedefs - native
assert statedefs == native_numbers | remaining

# Every natively lowered number must actually exist in the pinned source,
# and every classified number must come from a known source file.
for number in statedefs:
    assert rows["sources"][number] and set(rows["sources"][number]) <= set(FILES)

# 46 native bodies agree with the documented source-checked lowering, and
# the pinned source still has exactly the 13 not-yet-lowered statedefs.
assert len(native_numbers) == 46, sorted(native_numbers)
assert remaining == {191, 800, 810, 1300, 1310, 1320, 1330, 1340, 1350,
                     1351, 3000, 3050, 3051}, sorted(remaining)
print(f"ZSS state coverage: {len(native_numbers)} native, "
      f"{len(remaining)} fallback statedefs OK")
