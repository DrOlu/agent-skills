"""Unit tests for export_tools.py — the menu exporter used by every instance.

Contract: tool modules must be import-safe (no side effects at top level),
missing files and import-unsafe modules fail with a clear SystemExit, and
the exported menu keeps name/description/parameters/triggers per entry.

The needle-dependent export path runs only when cactus-needle is installed
(SKIP in CI, RUN locally) — the import-safety checks always run.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import export_tools as et  # noqa: E402

NEEDLE = importlib.util.find_spec("needle") is not None


def write_module(name, body):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    open(p, "w").write(body)
    return p


class TestLoadModule(unittest.TestCase):
    def test_missing_file_system_exit(self):
        with self.assertRaises(SystemExit) as cm:
            et.load_module("/no/such/file_xyz.py")
        self.assertIn("no such file", str(cm.exception))

    def test_import_unsafe_module_system_exit_with_hint(self):
        # a module that raises at import must fail LOUDLY with the
        # import-safe hint, not with a bare traceback
        p = write_module("unsafe.py", "raise ValueError('boom at top level')\n")
        with self.assertRaises(SystemExit) as cm:
            et.load_module(p)
        self.assertIn("import-safe", str(cm.exception))
        self.assertIn("boom", str(cm.exception))

    def test_safe_module_loads(self):
        p = write_module("safe.py", "VALUE = 42\n")
        mod = et.load_module(p)
        self.assertEqual(mod.VALUE, 42)


@unittest.skipUnless(NEEDLE, "cactus-needle not installed for this interpreter")
class TestExportWithNeedle(unittest.TestCase):
    """Full export through the real @needle.tool decorator."""
    TOOL_BODY = '''
import needle

@needle.tool(triggers=["how many widgets", "count widgets"])
def widget_count() -> dict:
    """Count the widgets."""
    return {"count": 0}
'''

    def test_export_produces_menu_structure(self):
        import subprocess
        d = tempfile.mkdtemp()
        mod = os.path.join(d, "tools_def.py")
        open(mod, "w").write(self.TOOL_BODY)
        out = os.path.join(d, "menu.json")
        r = subprocess.run([sys.executable,
                             os.path.join(os.path.dirname(
                                 os.path.abspath(et.__file__)), "export_tools.py"),
                             mod, "-o", out],
                            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        menu = json.load(open(out))
        self.assertEqual(len(menu), 1)
        entry = menu[0]
        for key in ("name", "description", "parameters", "triggers"):
            self.assertIn(key, entry)
        self.assertEqual(entry["name"], "widget_count")
        self.assertIn("how many widgets", entry["triggers"])


if __name__ == "__main__":
    unittest.main()