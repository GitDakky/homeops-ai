"""Tests for homeops_ai/patch_hermes_prefix.py.

CI has no Hermes install, so these tests synthesize a minimal
``hermes_cli/dashboard_auth/prefix.py`` with the exact upstream v0.18.0
guard shape and run the patch script against it as a subprocess (the
script mutates sys.path/imports, so in-process invocation would leak).
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "homeops_ai" / "patch_hermes_prefix.py"

# Minimal but faithful reproduction of the upstream normalise_prefix()
# from hermes-agent v2026.7.1 (v0.18.0) hermes_cli/dashboard_auth/prefix.py.
UPSTREAM_PREFIX_PY = '''\
from typing import Optional

_REJECT_CHARS = frozenset(('"', "'", "<", ">", " ", "\\n", "\\r", "\\t"))


def normalise_prefix(raw: Optional[str]) -> str:
    if not raw:
        return ""
    p = raw.strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    p = p.rstrip("/")
    if (
        "//" in p
        or ".." in p
        or any(c in p for c in _REJECT_CHARS)
    ):
        return ""
    if len(p) > 64:
        return ""
    return p
'''

SAMPLE = "/api/hassio_ingress/" + "A" * 43 + "/dashboard"


def make_fake_lib(root: pathlib.Path, source: str = UPSTREAM_PREFIX_PY) -> pathlib.Path:
    pkg = root / "hermes_cli" / "dashboard_auth"
    pkg.mkdir(parents=True)
    (root / "hermes_cli" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "prefix.py").write_text(source)
    return root


def run_patch(lib_dir: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(lib_dir)],
        capture_output=True,
        text=True,
    )


class PatchHermesPrefixTests(unittest.TestCase):
    def test_patches_and_verifies_ha_ingress_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            lib = make_fake_lib(pathlib.Path(td))
            result = run_patch(lib)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            patched = (lib / "hermes_cli" / "dashboard_auth" / "prefix.py").read_text()
            self.assertIn("if len(p) > 200:", patched)
            self.assertNotIn("if len(p) > 64:", patched)
            # The patched module must accept the real HA ingress shape.
            sys.path.insert(0, td)
            try:
                for mod in [m for m in list(sys.modules) if m.startswith("hermes_cli")]:
                    del sys.modules[mod]
                from hermes_cli.dashboard_auth.prefix import normalise_prefix
                self.assertEqual(normalise_prefix(SAMPLE), SAMPLE)
                # Safety properties preserved.
                self.assertEqual(normalise_prefix("/a/../b"), "")
                self.assertEqual(normalise_prefix("//double"), "")
                self.assertEqual(normalise_prefix("/x" * 200), "")
            finally:
                sys.path.remove(td)
                for mod in [m for m in list(sys.modules) if m.startswith("hermes_cli")]:
                    del sys.modules[mod]

    def test_idempotent_second_run(self):
        with tempfile.TemporaryDirectory() as td:
            lib = make_fake_lib(pathlib.Path(td))
            first = run_patch(lib)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = run_patch(lib)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already patched", second.stdout)

    def test_fails_loud_when_guard_shape_changes(self):
        changed = UPSTREAM_PREFIX_PY.replace("if len(p) > 64:", "if len(p) > 128:")
        with tempfile.TemporaryDirectory() as td:
            lib = make_fake_lib(pathlib.Path(td), source=changed)
            result = run_patch(lib)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("not found", result.stderr)

    def test_fails_loud_when_prefix_module_missing(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_patch(pathlib.Path(td))
            self.assertEqual(result.returncode, 2)

    def test_sample_prefix_matches_real_ha_ingress_length(self):
        # HA Supervisor tokens are 43 chars; full forwarded prefix is 73.
        self.assertEqual(len(SAMPLE), 73)
        self.assertGreater(len(SAMPLE), 64)


if __name__ == "__main__":
    unittest.main()
