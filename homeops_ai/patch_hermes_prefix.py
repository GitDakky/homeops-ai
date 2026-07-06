#!/usr/bin/env python3
"""Build-time patch: raise Hermes dashboard's X-Forwarded-Prefix length cap.

Hermes v0.18.0 (v2026.7.1) rejects any X-Forwarded-Prefix longer than 64
characters in ``hermes_cli/dashboard_auth/prefix.py``::

    if len(p) > 64:
        return ""

Home Assistant Supervisor ingress prefixes look like
``/api/hassio_ingress/<43-char-token>`` (63 chars). HomeOps AI forwards
``$ingress_prefix/dashboard`` (73 chars), so Hermes silently discards the
prefix, serves root-relative asset URLs (``/assets/…``), the browser asks
HA core for them, gets the HA frontend shell / 404s, and the dashboard
renders as a blank white page.

Upstream issue filed with NousResearch/hermes-agent; until a release ships
with a bigger (or no) cap, we patch the installed file at image build time.

Fail-loud contract:
  * If the exact guard line is not found (upstream changed the code), exit 2
    so the Docker build fails and the hermes-version-watch PR flags it.
  * After patching, import the module and verify a realistic 73-char HA
    ingress prefix survives normalisation; exit 3 otherwise.

Usage: patch_hermes_prefix.py [HERMES_LIB_DIR]   (default /usr/local/lib/hermes-agent)
"""
from __future__ import annotations

import pathlib
import shutil
import sys

OLD_GUARD = "if len(p) > 64:"
NEW_GUARD = "if len(p) > 200:"  # HA ingress prefix + /dashboard = 73; headroom for nesting

# Realistic shape: /api/hassio_ingress/ + 43-char Supervisor token + /dashboard
SAMPLE_PREFIX = "/api/hassio_ingress/" + "A" * 43 + "/dashboard"


def main() -> int:
    lib_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/hermes-agent")
    target = lib_dir / "hermes_cli" / "dashboard_auth" / "prefix.py"
    if not target.is_file():
        print(f"ERROR: {target} not found — Hermes install layout changed?", file=sys.stderr)
        return 2

    text = target.read_text(encoding="utf-8")
    if NEW_GUARD in text and OLD_GUARD not in text:
        print(f"already patched: {target}")
    elif OLD_GUARD in text:
        if text.count(OLD_GUARD) != 1:
            print(f"ERROR: expected exactly one occurrence of {OLD_GUARD!r} in {target}", file=sys.stderr)
            return 2
        target.write_text(text.replace(OLD_GUARD, NEW_GUARD), encoding="utf-8")
        print(f"patched: {target}  ({OLD_GUARD!r} -> {NEW_GUARD!r})")
    else:
        print(
            f"ERROR: guard line {OLD_GUARD!r} not found in {target}.\n"
            "Upstream prefix.py changed — re-check whether the 64-char cap still "
            "exists (it may be fixed upstream; if so, drop this patch).",
            file=sys.stderr,
        )
        return 2

    # Drop stale bytecode so the patched source is what actually gets imported.
    pycache = target.parent / "__pycache__"
    if pycache.is_dir():
        shutil.rmtree(pycache)

    # Verify against the real import path.
    sys.path.insert(0, str(lib_dir))
    from hermes_cli.dashboard_auth.prefix import normalise_prefix  # noqa: E402

    got = normalise_prefix(SAMPLE_PREFIX)
    if got != SAMPLE_PREFIX:
        print(
            f"ERROR: verification failed: normalise_prefix({SAMPLE_PREFIX!r}) -> {got!r} "
            f"(expected the prefix back)",
            file=sys.stderr,
        )
        return 3
    # Safety properties must survive the patch.
    for hostile in ("/a/../b", "//double", "/has space", '/<script>', "/x" * 200):
        if normalise_prefix(hostile) != "":
            print(f"ERROR: hostile prefix {hostile!r} was NOT rejected after patch", file=sys.stderr)
            return 3
    print(f"verified: normalise_prefix accepts {len(SAMPLE_PREFIX)}-char HA ingress prefix; hostile inputs still rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
