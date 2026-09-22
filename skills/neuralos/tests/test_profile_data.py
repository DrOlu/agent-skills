"""Unit tests for profile_data.py — the Phase-1 profiler's type inference.

Pins the live-lesson fixes: only strings become enum candidates (a Literal of
observed datetimes breaks on the next day's data — hit live on chinook), and
all-null columns must not be misdetected as datetime.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import profile_data as pd_  # noqa: E402


class TestSniffDatetime(unittest.TestCase):
    def test_iso(self):
        self.assertIsNotNone(pd_.sniff_datetime("2026-09-22T10:00:00"))
        self.assertIsNotNone(pd_.sniff_datetime("2026-09-22"))
        self.assertIsNotNone(pd_.sniff_datetime("22/09/2026 10:00:00"))

    def test_garbage_is_none(self):
        self.assertIsNone(pd_.sniff_datetime("not a date"))
        self.assertIsNone(pd_.sniff_datetime(""))


class TestInferType(unittest.TestCase):
    def test_integer(self):
        self.assertEqual(pd_.infer_type([1, 2, 3]), "integer")
        self.assertEqual(pd_.infer_type(["-5"]), "integer")

    def test_number(self):
        self.assertEqual(pd_.infer_type([1.5, 2]), "number")

    def test_boolean(self):
        self.assertEqual(pd_.infer_type(["true", "false", "yes", "no"]),
                         "boolean")

    def test_datetime(self):
        self.assertEqual(pd_.infer_type(["2026-09-22", "2026-09-23"]),
                         "datetime")

    def test_string(self):
        self.assertEqual(pd_.infer_type(["hello", "world"]), "string")


class TestProfileField(unittest.TestCase):
    def test_integer_min_max(self):
        f = pd_.profile_field("n", [3, 1, 2])
        self.assertEqual(f["detected_type"], "integer")
        self.assertEqual((f["min"], f["max"]), (1, 3))
        self.assertFalse(f["nullable"])

    def test_string_lengths_and_enum(self):
        # 3 distinct in 4 rows -> low-cardinality string becomes enum candidate
        f = pd_.profile_field("kind", ["a", "b", "a", "c"])
        self.assertEqual(f["detected_type"], "string")
        self.assertEqual(f["enum_values"], ["a", "b", "c"])
        self.assertEqual(f["python_type"], "Literal")
        self.assertEqual((f["min_len"], f["max_len"]), (1, 1))

    def test_high_cardinality_string_never_enum(self):
        f = pd_.profile_field("name", ["a", "b", "c", "d"])
        self.assertNotIn("enum_values", f)  # distinct == len(nonnull)
        self.assertEqual(f["python_type"], "str")

    def test_datetime_never_enum(self):
        # THE chinook fix: few distinct datetimes must stay datetime
        f = pd_.profile_field("created", ["2026-09-01", "2026-09-01",
                                          "2026-09-02"])
        self.assertEqual(f["detected_type"], "datetime")
        self.assertNotIn("enum_values", f)
        self.assertEqual(f["python_type"], "datetime")
        self.assertIn("datetime_format", f)

    def test_all_null_is_optional_string_not_datetime(self):
        # the all([]) misdetection bug: every value null must not become datetime
        f = pd_.profile_field("x", [None, None, None])
        self.assertEqual(f["python_type"], "Optional[str]")
        self.assertEqual(f["detected_type"], "string")
        self.assertTrue(f["nullable"])
        self.assertEqual(f["null_count"], 3)
        self.assertIn("empty", f["note"])

    def test_null_count_and_nullable(self):
        f = pd_.profile_field("x", [1, None, 2])
        self.assertEqual(f["null_count"], 1)
        self.assertTrue(f["nullable"])
        self.assertEqual((f["min"], f["max"]), (1, 2))

    def test_sample_values_deduped_capped(self):
        f = pd_.profile_field("s", [str(i) for i in range(20)])
        self.assertLessEqual(len(f["sample_values"]), 8)
        self.assertEqual(len(f["sample_values"]),
                         len(set(f["sample_values"])))


class TestJsonSafe(unittest.TestCase):
    def test_scalars_passthrough(self):
        self.assertEqual(pd_.sample_jsonsafe(5), 5)
        self.assertTrue(pd_.sample_jsonsafe(True) is True)
        self.assertIsNone(pd_.sample_jsonsafe(None))

    def test_nested(self):
        row = {"a": {"b": 1}}
        out = pd_.jsonsafe_row(row)
        self.assertEqual(out, {"a_b": 1} if "a_b" in out else out)


if __name__ == "__main__":
    unittest.main()