#!/usr/bin/env python3
"""Fetch the pinned upstream checkouts the converters and the oracle read.

    python scripts/fetch_external.py [--dest DIR]

Pins live in scripts/external-pins.env. The checkouts land in .external/ (or
$IKEMEN_EXTERNAL_DIR, or --dest) and are never committed. Re-running is cheap:
a checkout already at its pinned commit is left alone.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_pins() -> dict:
    pins = {}
    for line in (ROOT / "scripts" / "external-pins.env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            pins[key] = value
    return pins


def git(*args: str, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True,
                            capture_output=True, check=False)
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result.stdout.strip()


def fetch(dest: Path, name: str, url: str, sha: str) -> None:
    repo = dest / name
    if not (repo / ".git").is_dir():
        repo.mkdir(parents=True, exist_ok=True)
        git("init", "-q", cwd=repo)
        git("remote", "add", "origin", url, cwd=repo)
    if git("rev-parse", "-q", "--verify", "HEAD", cwd=repo, check=False) != sha:
        git("fetch", "-q", "--depth", "1", "origin", sha, cwd=repo)
        git("checkout", "-q", "--force", sha, cwd=repo)
    print(f"{name} @ {git('rev-parse', 'HEAD', cwd=repo)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path,
                        default=Path(os.environ.get("IKEMEN_EXTERNAL_DIR",
                                                    ROOT / ".external")))
    args = parser.parse_args()
    pins = read_pins()
    args.dest.mkdir(parents=True, exist_ok=True)
    fetch(args.dest, "Ikemen-GO", pins["IKEMEN_GO_URL"], pins["IKEMEN_GO_SHA"])
    fetch(args.dest, "Ikemen-GO-Screenpack",
          pins["IKEMEN_SCREENPACK_URL"], pins["IKEMEN_SCREENPACK_SHA"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
