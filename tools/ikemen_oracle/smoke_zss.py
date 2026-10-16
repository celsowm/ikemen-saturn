#!/usr/bin/env python3
"""Exercise real generated mixed KFM/ZSS assets in the native Saturn runner.

This is NOT Ikemen GO parity. It catches classic-only trace wiring, wrong
player identity, vacuous scripted punches, and truncated JSON frame output
on normal CI runs without Go/SDL.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ikemen_oracle.run_saturn import character_asset  # noqa: E402


def check(bin_path: Path) -> None:
    scenarios = ROOT / "tools" / "ikemen_oracle" / "scenarios"
    cases = [
        ("zss_p2_idle_120.json", None, None),
        ("zss_p1_stand_x_160.json", 0, 200),
        ("zss_p2_stand_x_200.json", 1, 200),
        ("zss_p2_fast_palm_240.json", 1, 1025),
    ]
    with tempfile.TemporaryDirectory(prefix="zss-oracle-smoke-") as tmp:
        for name, fighter, state in cases:
            scenario = scenarios / name
            spec = json.loads(scenario.read_text(encoding="utf-8"))
            assert character_asset(spec["p1"]) in ("kfm", "kfm_zss")
            assert character_asset(spec["p2"]) in ("kfm", "kfm_zss")
            destination = Path(tmp) / scenario.stem / "trace.jsonl"
            subprocess.run([
                sys.executable, str(ROOT / "tools/ikemen_oracle/run_saturn.py"),
                str(scenario), "--trace", str(destination),
                "--trace-bin", str(bin_path)
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            rows = [json.loads(line) for line in destination.read_text(
                encoding="utf-8").splitlines() if line]
            assert len(rows) == spec["frames"], (name, len(rows))
            assert all(r["schema"] == 1 and len(r["chars"]) >= 2
                       for r in rows), name
            if state is not None:
                visited = {r["chars"][fighter]["state_no"] for r in rows}
                assert state in visited, (name, state, sorted(visited))
            print(f"ZSS native trace: {name} ({len(rows)} frames) OK")

        # The raw trace executable refuses an unsupported source token.
        bad = subprocess.run([
            str(bin_path), str(Path(tmp) / "invalid.jsonl"),
            "1", "1", str(Path(tmp) / "invalid-input.txt"),
            "", "kfm", "unknown"],
            cwd=ROOT, capture_output=True, text=True)
        assert bad.returncode == 2, bad.stderr
        assert "unsupported Saturn oracle character" in bad.stderr


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-bin", required=True, type=Path)
    args = parser.parse_args()
    check(args.trace_bin.resolve())
