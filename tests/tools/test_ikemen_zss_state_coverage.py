#!/usr/bin/env python3
"""ZSS state coverage: numbers must match the pinned source and lowering."""
from __future__ import annotations

from pathlib import Path

from tools.ikemen_zss_character_states import CHARACTER_STATES, HIT_STATES
from tools.ikemen_zss_state_coverage import FILES, inventory

native = set(CHARACTER_STATES) | set(HIT_STATES)
assert len(CHARACTER_STATES) == 37, "kfm.zss native set changed"
assert len(HIT_STATES) == 6, "hits.zss native set changed"

char_dir = Path(".external/Ikemen-GO-Screenpack/chars/kfm_zaxis")
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

# 43 native bodies agree with the documented source-checked lowering.
assert len(native_numbers) == 43, sorted(native_numbers)
print(f"ZSS state coverage: {len(native_numbers)} native, "
      f"{len(remaining)} fallback statedefs OK")
