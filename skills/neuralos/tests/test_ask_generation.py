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
        for line in self.code.splitlines():
            code_line = line.split('#')[0]
            self.assertNotIn('function_calls', code_line,
                             f'executable use of function_calls: {line!r}')

    def test_results_based_gating_present(self):
        self.assertIn('results in (None, [], {})', self.code)
        self.assertIn("no results produced", self.code)
        self.assertIn("SystemExit(2)", self.code)

    def test_deterministic_fast_path_present(self):
        self.assertIn("deterministic:", self.code)
        self.assertIn("load_enum_cages", self.code)
        self.assertIn('"enum"', self.code)

    def test_possessive_normalization_present(self):
        self.assertIn("normalize_possessive", self.code)
        self.assertIn("'s", self.code)

    def test_never_prints_without_results(self):
        """The only json.dumps(results)-style prints must come after the
        empty-results guard."""
        prints = [i for i, line in enumerate(self.code.splitlines())
                  if "print(json.dumps(results" in line]
        guard = [i for i, line in enumerate(self.code.splitlines())
                 if "no results produced" in line]
        self.assertTrue(guard, "empty-results guard missing")
        self.assertTrue(prints)
        for p in prints:
            self.assertGreater(p, guard[0],
                               "results printed BEFORE the stale-data guard")


if __name__ == "__main__":
    unittest.main()
