"""CNS section parsing and state collection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    from tools.ikemen_text import read_mugen_text
except ModuleNotFoundError:  # direct `python tools/ikemen_cns.py` invocation
    from ikemen_text import read_mugen_text


@dataclass
class Section:
    name: str
    values: list[tuple[str, str]] = field(default_factory=list)
    runtime_trigger_expr: list[dict] | None = None
    runtime_value0_expr: list[dict] | None = None
    runtime_value1_expr: list[dict] | None = None

    def all(self, key: str) -> list[str]:
        key = key.lower()
        return [value for k, value in self.values if k.lower() == key]

    def get(self, key: str, default: str | None = None) -> str | None:
        values = self.all(key)
        return values[-1] if values else default


def trigger_indices(section: Section) -> list[int]:
    """Return numbered trigger groups present in a parsed CNS section."""
    return sorted({
        int(match.group(1))
        for key, _ in section.values
        if (match := re.fullmatch(r"trigger(\d+)", key.strip(), re.I))
    })


@dataclass
class State:
    number: int
    statedef: Section
    controllers: list[Section]


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def parse_sections(path: Path) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    for raw in read_mugen_text(path).splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = Section(line[1:-1].strip())
            sections.append(current)
            continue
        if current is not None and "=" in line:
            key, value = line.split("=", 1)
            current.values.append((key.strip(), value.strip()))
    return sections


def select_state_numbers(spec: str, sources: list[Path]) -> list[int]:
    """Resolve an explicit state list or every Statedef in the source files."""
    if spec.strip().casefold() != "all":
        return [int(value.strip()) for value in spec.split(",") if value.strip()]
    sections: list[Section] = []
    for source in sources:
        sections.extend(parse_sections(source))
    _, states = collect_states(sections)
    return sorted({state.number for state in states})


def collect_states(
    sections: list[Section],
) -> tuple[dict[str, Section], list[State]]:
    globals_: dict[str, Section] = {}
    states: list[State] = []
    current: State | None = None

    for section in sections:
        m = re.fullmatch(r"Statedef\s+(-?\d+)", section.name, flags=re.I)
        if m:
            current = State(int(m.group(1)), section, [])
            states.append(current)
        elif re.match(r"State\s+", section.name, flags=re.I):
            if current is not None:
                current.controllers.append(section)
        else:
            globals_[section.name.lower()] = section

    return globals_, states
