"""Unit tests for laya_router.py — the OPTIONAL decision-model seam.

Pins the contracts that make the seam safe to ship:
- import-safety: the module must import on machines WITHOUT laya/torch
  (live calls raise a guided ImportError at run time, not import time);
- compact_criterion never emits a dangling half-parenthetical (a real
  pilot bug: word-capping inside '(e.g. ...' produced '(e.g. (e.g. …');
- the calibrated-bucket guard (choice >10 options -> uncalibrated);
- the escalation rule (None confidence escalates — an unanswered question
  must never look confident).
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import laya_router as lr  # noqa: E402


class TestImportSafety(unittest.TestCase):
    def test_module_imports_without_laya(self):
        # importing the module must not have pulled laya or torch in
        for bad in ("laya", "torch"):
            self.assertNotIn(bad, sys.modules,
                             f"{bad} imported at module load — the router "
                             f"must stay importable without it")


class TestCompactCriterion(unittest.TestCase):
    def test_short_description_unchanged(self):
        out = lr.compact_criterion("Count invoices.", ["count invoices"])
        self.assertEqual(out, "Count invoices. (e.g. count invoices)")

    def test_long_description_capped_at_max_words(self):
        out = lr.compact_criterion(" ".join(["word"] * 40) + ".", ["t1"], 10)
        words = out.split("(e.g.")[0].split()
        self.assertLessEqual(len(words), 10)

    def test_no_dangling_half_parenthetical(self):
        # the pilot bug: cap cut inside '(e.g. a search box for tracks)'
        desc = "Find tracks by name fragment (a search box for tracks). Extra sentence."
        out = lr.compact_criterion(desc, ["find track"], 6)
        self.assertNotIn("(e.g. (e.g.", out)
        self.assertEqual(out.count("("), out.count(")"))

    def test_trigger_only_added_when_no_eg_already(self):
        out = lr.compact_criterion("Already has (e.g. something) here.", ["t"])
        self.assertNotIn("(e.g. t)", out)

    def test_empty_description_safe(self):
        out = lr.compact_criterion("", [], 10)
        self.assertEqual(out, "")


class TestBuildCriteria(unittest.TestCase):
    def test_menu_shapes(self):
        menu = [
            {"name": "p1", "description": "Does one thing well.", "triggers": ["x"]},
            {"name": "p2", "description": "Does another."},
        ]
        crit = lr.build_criteria(menu)
        self.assertEqual(set(crit), {"p1", "p2"})
        self.assertIn("(e.g. x)", crit["p1"])
        self.assertNotIn("(e.g.", crit["p2"])


class TestCalibrationGuard(unittest.TestCase):
    def test_ten_options_calibrated(self):
        q = {"type": "choice", "criteria": {f"o{i}": "x" for i in range(10)}}
        self.assertFalse(lr.uncalibrated(q))
        self.assertEqual(lr.option_count(q), 10)

    def test_eleven_options_uncalibrated(self):
        q = {"type": "choice", "criteria": {f"o{i}": "x" for i in range(11)}}
        self.assertTrue(lr.uncalibrated(q))
        self.assertEqual(lr.option_count(q), 11)

    def test_list_criteria_counted(self):
        self.assertEqual(lr.option_count({"type": "choice",
                                          "criteria": ["a", "b"]}), 2)

    def test_non_choice_ignored(self):
        q = {"type": "noul", "criteria": {"true": "t", "false": "f"}}
        self.assertFalse(lr.uncalibrated(q))
        self.assertEqual(lr.option_count(q), 2)

    def test_malformed_safe(self):
        self.assertFalse(lr.uncalibrated(None))
        self.assertFalse(lr.uncalibrated({}))
        self.assertEqual(lr.option_count({}), 0)
        self.assertEqual(lr.option_count("junk"), 0)


class TestEscalation(unittest.TestCase):
    def test_below_threshold_escalates(self):
        self.assertTrue(lr.escalates(0.42, 0.7))

    def test_at_or_above_threshold_passes(self):
        self.assertFalse(lr.escalates(0.70, 0.7))
        self.assertFalse(lr.escalates(0.95, 0.7))

    def test_none_confidence_escalates(self):
        # an unanswered / no_match result must never look confident
        self.assertTrue(lr.escalates(None, 0.7))


if __name__ == "__main__":
    unittest.main()