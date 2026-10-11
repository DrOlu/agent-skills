#!/usr/bin/env python3
"""Unit tests for scripts/gate_conformance.py — the black-box GATE_VERSION 1
conformance suite (the fleet fixture harness from DrOlu/ReactorPro#107).

Pins the runner's contract, NOT any one gate implementation:
  * menu loading accepts all three documented shapes and rejects others
  * the built-in matrix derives the four case families from a menu, and
    SKIPS (never fails) the action/dropped-filter cases a menu legitimately
    cannot exhibit
  * answered/refused/exit expectations check exit code + envelope fields,
    including the legacy-key and gate_version contracts
  * refusal_reason matching is by FAMILY (parameterized variants match)
  * main() exits 0 when all cases pass, 1 on any failure
"""
import json
import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import gate_conformance as gc  # noqa: E402

MENU = [
    {"name": "count_rows",
     "description": "Count the rows in the dataset.",
     "triggers": ["count rows", "how many rows", "row count"],
     "parameters": {"type": "object",
                    "properties": {"dataset": {"type": "string",
                                               "enum": ["ledger"]}},
                    "required": []}},
    {"name": "get_page",
     "description": "Read one page of the report by number.",
     "triggers": ["show page", "page content", "read page"],
     "parameters": {"type": "object",
                    "properties": {"n": {"type": "integer",
                                         "pattern": "page\\s+(\\d{1,3})"}},
                    "required": ["n"]}},
]

# A stub ask.py that behaves like the generated gate contract, so the
# conformance runner can be tested end-to-end without the generator.
STUB_ASK = textwrap.dedent("""
    import json, sys
    q = sys.argv[1].lower()
    menu = json.load(open("needle_menu.json", encoding="utf-8"))
    menu = menu if isinstance(menu, list) else menu.get("menu") or menu.get("probes")
    vocab = set()
    for p in menu:
        for t in p.get("triggers", []):
            vocab |= set(t.lower().replace("-", " ").split())
        vocab |= set(p["name"].replace("_", " ").split())
    def emit(env, code):
        print(json.dumps(env))
        raise SystemExit(code)
    base = {"ask_id": "stub", "ts": 0.0, "question": q, "normalized": q,
            "confidence": 0.9, "latency_ms": 1, "menu_version": "stub",
            "gate_version": 1}
    if q.startswith("delete") or q.startswith("wipe"):
        emit({**base, "probe": None, "mode": "refused", "refused": True,
              "refusal_reason": "action_intent", "results": None,
              "candidates_retrieved": ["count_rows"]}, 2)
    if "frobnicate" in q:
        emit({**base, "probe": None, "mode": "refused", "refused": True,
              "refusal_reason": "no_probe_matches(unknown=widget)",
              "results": None, "candidates_retrieved": []}, 2)
    if "blocked" in q and "archived" in q:
        emit({**base, "probe": None, "mode": "refused", "refused": True,
              "refusal_reason": "dropped_filter:blocked",
              "results": None, "candidates_retrieved": []}, 2)
    for p in menu:
        for t in p.get("triggers", []):
            if all(w in q for w in t.lower().split()):
                emit({**base, "probe": p["name"], "mode": "retrieval",
                      "refused": False, "refusal_reason": None,
                      "results": [{"_tool": p["name"]}]}, 0)
    emit({**base, "probe": "count_rows", "mode": "retrieval",
          "refused": False, "refusal_reason": None, "results": []}, 0)
""")


class TestMenuLoading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        with open(os.path.join(self.dir, "ask.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_ASK)

    def tearDown(self):
        self.tmp.cleanup()

    def write_menu(self, payload):
        with open(os.path.join(self.dir, "needle_menu.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(payload, fh)

    def test_bare_array_shape(self):
        self.write_menu(MENU)
        self.assertEqual(len(gc.load_menu(self.dir)), 2)

    def test_menu_key_shape(self):
        self.write_menu({"name": "x", "version": "1", "menu": MENU})
        self.assertEqual(len(gc.load_menu(self.dir)), 2)

    def test_probes_key_shape(self):
        self.write_menu({"probes": MENU})
        self.assertEqual(len(gc.load_menu(self.dir)), 2)

    def test_metadata_only_object_rejected(self):
        self.write_menu({"name": "x", "version": "1"})
        with self.assertRaises(SystemExit):
            gc.load_menu(self.dir)


class TestDerivedMatrix(unittest.TestCase):
    def test_four_case_families_derived(self):
        cases = gc.derive_cases(MENU)
        labels = [c.get("label", "") for c in cases]
        self.assertTrue(any(l.startswith("first-trigger:count_rows") for l in labels))
        self.assertTrue(any(l.startswith("first-trigger:get_page") for l in labels))
        self.assertIn("action-verb", labels)
        self.assertTrue(any(l.startswith("dropped-filter:") for l in labels))
        self.assertIn("unknown-subject", labels)

    def test_action_case_skipped_when_menu_claims_the_verb(self):
        menu = [dict(MENU[0]),
                {"name": "delete_records",
                 "description": "Remove records by id.",
                 "triggers": ["delete records", "remove record"],
                 "parameters": {"type": "object", "properties": {}, "required": []}}]
        cases = gc.derive_cases(menu)
        self.assertNotIn("action-verb", [c.get("label") for c in cases])

    def test_every_first_trigger_case_targets_its_probe(self):
        cases = gc.derive_cases(MENU)
        for case in cases:
            if case.get("label", "").startswith("first-trigger:"):
                self.assertEqual(case["expect"], "answered")
                self.assertTrue(case["probe"])


class TestCheckCase(unittest.TestCase):
    """check_case against the stub ask.py, running as a real subprocess."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = cls.tmp.name
        with open(os.path.join(cls.dir, "ask.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_ASK)
        with open(os.path.join(cls.dir, "needle_menu.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(MENU, fh)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, case):
        return gc.check_case(case, self.dir, sys.executable, timeout=60)

    def test_answered_first_trigger(self):
        status, detail = self.run_case({"question": "count rows",
                                        "expect": "answered",
                                        "probe": "count_rows"})
        self.assertEqual(status, "pass")

    def test_answered_wrong_probe_fails(self):
        status, _ = self.run_case({"question": "count rows",
                                   "expect": "answered", "probe": "get_page"})
        self.assertEqual(status, "fail")

    def test_refused_action_intent(self):
        status, detail = self.run_case({"question": "delete all the rows",
                                        "expect": "refused",
                                        "reason": "action_intent"})
        self.assertEqual(status, "pass")

    def test_refused_reason_family_matching(self):
        status, _ = self.run_case({"question": "frobnicate the widget",
                                   "expect": "refused",
                                   "reason": "no_probe_matches"})
        self.assertEqual(status, "pass")

    def test_refused_wrong_family_fails(self):
        status, _ = self.run_case({"question": "frobnicate the widget",
                                   "expect": "refused",
                                   "reason": "action_intent"})
        self.assertEqual(status, "fail")

    def test_precondition_violation_is_skip_not_fail(self):
        # the stub happily answers "count rows" — an expectation that it be
        # REFUSED is this menu's precondition not holding: SKIP
        status, detail = self.run_case({"question": "count rows",
                                        "expect": "refused"})
        self.assertEqual(status, "skip")

    def test_raw_exit_expectation(self):
        status, _ = self.run_case({"question": "wipe the archive",
                                   "expect": "exit", "code": 2})
        self.assertEqual(status, "pass")

    def test_unknown_expect_fails(self):
        status, _ = self.run_case({"question": "x", "expect": "teleport"})
        self.assertEqual(status, "fail")


class TestMainExitCodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = cls.tmp.name
        with open(os.path.join(cls.dir, "ask.py"), "w", encoding="utf-8") as fh:
            fh.write(STUB_ASK)
        with open(os.path.join(cls.dir, "needle_menu.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(MENU, fh)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def write_cases(self, cases):
        path = os.path.join(self.dir, "cases.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cases, fh)
        return path

    def test_all_pass_exits_zero(self):
        rc = gc.main(["--instance", self.dir, "--python", sys.executable,
                      "--cases", self.write_cases([
                          {"question": "count rows", "expect": "answered",
                           "probe": "count_rows"},
                          {"question": "delete all the rows", "expect": "refused",
                           "reason": "action_intent"}])])
        self.assertEqual(rc, 0)

    def test_any_failure_exits_one(self):
        rc = gc.main(["--instance", self.dir, "--python", sys.executable,
                      "--cases", self.write_cases([
                          {"question": "count rows", "expect": "answered",
                           "probe": "count_rows"},
                          {"question": "count rows", "expect": "answered",
                           "probe": "get_page"}])])
        self.assertEqual(rc, 1)

    def test_builtin_matrix_exits_zero_on_contract_stub(self):
        rc = gc.main(["--instance", self.dir, "--python", sys.executable])
        self.assertEqual(rc, 0)

    def test_missing_ask_py_is_usage_error(self):
        with self.assertRaises(SystemExit):
            gc.main(["--instance", os.path.join(self.dir, "empty")])


if __name__ == "__main__":
    unittest.main()
