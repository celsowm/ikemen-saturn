#!/usr/bin/env python3
"""Suite status tool: classification rows without running any engine."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.ikemen_oracle.suite_status import classify, fmt

scenario = {
    "name": "example_200", "frames": 200,
}


def report(frames_compared, first_difference):
    return {
        "schema": 1, "frames_upstream": frames_compared,
        "frames_saturn": frames_compared,
        "frames_compared": frames_compared,
        "first_difference": first_difference,
    }


with TemporaryDirectory() as temp:
    suite = Path(temp)
    scenario_file = suite / "scenario.json"
    scenario_file.write_text(json.dumps(scenario), encoding="utf-8")

    # No report yet: the scenario is simply pending, never a failure by itself.
    row = classify(scenario_file, suite)
    assert row["status"] == "MISSING" and row["frames"] == 200
    assert row["reported_frames"] is None
    assert fmt(row).startswith("MISSING")

    # A first divergence pins the report to the exact frame/field.
    out = suite / "example_200"
    out.mkdir()
    first = {"frame": 7, "side": "p1", "field": "state_no",
             "detail": "11 != 12"}
    (out / "zss_report.json").write_text(
        json.dumps(report(200, first)), encoding="utf-8")
    row = classify(scenario_file, suite)
    assert row["status"] == "DIFF" and row["reported_frames"] == 200
    assert row["first_difference"]["frame"] == 7
    assert "frame 7 p1.state_no" in fmt(row)

    # Malformed JSON must be reported explicitly, not misread as a match.
    (out / "zss_report.json").write_text("{broken", encoding="utf-8")
    assert classify(scenario_file, suite)["status"] == "BROKEN"

    # A clean report is an OK row, and the strict gate accepts only those.
    (out / "zss_report.json").write_text(
        json.dumps(report(200, None)), encoding="utf-8")
    row = classify(scenario_file, suite)
    assert row["status"] == "OK"
    assert "200 frames compared" in fmt(row)

print("oracle suite status classification OK")
