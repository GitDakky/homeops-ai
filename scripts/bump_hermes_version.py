#!/usr/bin/env python3
"""Bump the bundled Hermes Agent version across the repo.

Updates, atomically and consistently:
  1. homeops_ai/Dockerfile      — ARG HERMES_VERSION=<tag>
  2. homeops_ai/config.yaml     — add-on version (patch bump)
  3. homeops_ai/CHANGELOG.md    — new top entry
  4. DOCS.md                    — bundled release line

Usage:
  python3 scripts/bump_hermes_version.py <hermes-tag>          # e.g. v2026.7.1
  python3 scripts/bump_hermes_version.py --check               # exit 1 if behind

--check compares the pinned tag with the latest GitHub release of
NousResearch/hermes-agent and prints both; exit code 1 means an update is
available (used by the scheduled workflow).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "homeops_ai" / "Dockerfile"
CONFIG = ROOT / "homeops_ai" / "config.yaml"
CHANGELOG = ROOT / "homeops_ai" / "CHANGELOG.md"
DOCS = ROOT / "DOCS.md"

UPSTREAM_API = "https://api.github.com/repos/NousResearch/hermes-agent/releases/latest"
TAG_RE = re.compile(r"^v\d{4}\.\d{1,2}\.\d{1,2}(\.\d+)?$")


def pinned_tag() -> str:
    m = re.search(r"^ARG HERMES_VERSION=(\S+)$", DOCKERFILE.read_text(), re.M)
    if not m:
        raise SystemExit("ERROR: ARG HERMES_VERSION not found in Dockerfile")
    return m.group(1)


def latest_tag() -> str:
    req = urllib.request.Request(UPSTREAM_API, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["tag_name"]


def tag_key(tag: str) -> tuple[int, ...]:
    return tuple(int(p) for p in tag.lstrip("v").split("."))


def bump_addon_version() -> str:
    text = CONFIG.read_text()
    m = re.search(r'^version: "(\d+)\.(\d+)\.(\d+)"$', text, re.M)
    if not m:
        raise SystemExit("ERROR: version not found in config.yaml")
    new = f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}"
    CONFIG.write_text(text.replace(m.group(0), f'version: "{new}"', 1))
    return new


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    current = pinned_tag()

    if sys.argv[1] == "--check":
        latest = latest_tag()
        behind = tag_key(latest) > tag_key(current)
        print(f"pinned={current} latest={latest} behind={'yes' if behind else 'no'}")
        return 1 if behind else 0

    new_tag = sys.argv[1]
    if not TAG_RE.match(new_tag):
        raise SystemExit(f"ERROR: {new_tag!r} does not look like a hermes-agent tag (vYYYY.M.D)")
    if new_tag == current:
        print(f"Already pinned to {new_tag}; nothing to do.")
        return 0

    # 1. Dockerfile pin
    DOCKERFILE.write_text(
        re.sub(r"^ARG HERMES_VERSION=\S+$", f"ARG HERMES_VERSION={new_tag}",
               DOCKERFILE.read_text(), count=1, flags=re.M)
    )
    # 2. add-on version patch bump
    addon_version = bump_addon_version()
    # 3. changelog entry
    entry = (
        f"# Changelog\n\n## [{addon_version}]\n\n### Changed\n"
        f"- Bundled Hermes Agent updated from `{current}` to `{new_tag}` "
        f"([release notes](https://github.com/NousResearch/hermes-agent/releases/tag/{new_tag})).\n"
    )
    CHANGELOG.write_text(CHANGELOG.read_text().replace("# Changelog\n", entry, 1))
    # 4. DOCS.md bundled-release line
    DOCS.write_text(
        re.sub(r"\*\*Bundled Hermes Agent release:\*\* `\S+`",
               f"**Bundled Hermes Agent release:** `{new_tag}`",
               DOCS.read_text(), count=1)
    )

    print(f"Bumped Hermes {current} -> {new_tag}; add-on version {addon_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
