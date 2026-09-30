#!/usr/bin/env python3
"""Unit tests for the generated ask.py — the MANDATED structured-retrieval
entry point (operating rule 8).

Pins the reliability contract learned in live use (needle 3.0.3):
  * ask.py is generated for python-runtime instances
  * deterministic fast path for enum-caged rank-1 probes (selector bypass)
  * results-based gating — NEVER branches on function_calls (always empty
    in 3.0.3, and stale results must never be printed)
  * possessive normalization uses the menu's own enum values
  * stale-data guard exits 2 with an explicit error payload
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import gen_needle_instance as gi  # noqa: E402


class TestAskPyTemplate(unittest.TestCase):
    def setUp(self):
        self.code = gi.ASK_PY

    def test_parses(self):
        ast.parse(self.code)

    def test_no_function_calls_gating(self):
        """The 3.0.3 trap: function_calls is empty even on success — the
        generated entry point must never READ or branch on it. (Mentions in
        comments explaining the trap are fine.)"""
        self.assertNotIn('.get("function_calls"', self.code)
        self.assertNotIn(".get('function_calls'", self.code)
        # scan only executable lines (docstring mentions of the trap are fine)
        import io, tokenize
        toks = tokenize.generate_tokens(io.StringIO(self.code).readline)
        for tok in toks:
            if tok.type == tokenize.STRING:
                continue
            if tok.type == tokenize.NAME and "function_calls" in tok.string:
                self.fail(f"executable use of function_calls at {tok.start}")

    def test_results_based_gating_present(self):
        self.assertIn('results in (None, [], {})', self.code)
        self.assertIn("no results produced", self.code)
        self.assertIn("SystemExit(2)", self.code)

    def test_deterministic_fast_path_present(self):
        self.assertIn("deterministic:", self.code)
        self.assertIn("load_cages", self.code)
        self.assertIn("extract_args", self.code)
        self.assertIn('"enum"', self.code)

    def test_possessive_normalization_present(self):
        self.assertIn("normalize_possessive", self.code)
        self.assertIn("'s", self.code)

    def test_never_prints_without_results(self):
        """Every answer path must go through emit() AFTER the empty-results
        guard; no path may print raw results before it."""
        lines = self.code.splitlines()
        guard = [i for i, line in enumerate(lines)
                 if "no results produced" in line]
        self.assertTrue(guard, "empty-results guard missing")
        emits = [i for i, line in enumerate(lines) if "emit(env)" in line]
        self.assertGreaterEqual(len(emits), 2, "emit(env) missing")
        for e in emits:
            if e < guard[0]:
                # pre-guard emits must be EITHER error paths (SystemExit 2)
                # OR cache hits (which serve THIS question's own cached
                # payload keyed by question+menu version — never stale data
                # from another question)
                window = "\n".join(lines[e:e + 3])
                ok = ("SystemExit(2)" in window
                      or '"cached": True' in window
                      or '"cached": True' in "\n".join(lines[max(0, e - 8):e + 3]))
                self.assertTrue(ok, "pre-guard emit is neither an error path "
                                    f"nor a cache hit: {window[:120]!r}")
        self.assertNotIn('print(json.dumps(results', self.code)


if __name__ == "__main__":
    unittest.main()
