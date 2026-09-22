"""Unit tests for gen_needle_instance.py — Phase-3 menu emission.

Pins the grammar-caging rules: enum fields respect ENUM_MAX (12), numeric
fields are identified for aggregates, and menu entries separate required
from optional parameters via the __optional__ marker.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import gen_needle_instance as gi  # noqa: E402


class TestNames(unittest.TestCase):
    def test_snake(self):
        self.assertEqual(gi.snake("Invoice Lines"), "invoice_lines")
        self.assertEqual(gi.snake("---"), "field")  # never empty

    def test_pascal(self):
        self.assertEqual(gi.pascal("invoice_lines"), "InvoiceLines")
        self.assertEqual(gi.pascal("..."), "Record")


class TestEnumFields(unittest.TestCase):
    def test_within_cap_included(self):
        fields = [{"name": "kind", "enum_values": ["a", "b"], "distinct": 2}]
        self.assertEqual(gi.enum_fields(fields), [("kind", ["a", "b"])])

    def test_over_cap_excluded(self):
        fields = [{"name": "kind", "enum_values": [str(i) for i in range(15)],
                   "distinct": 15}]
        self.assertEqual(gi.enum_fields(fields), [])

    def test_cap_boundary_is_inclusive(self):
        fields = [{"name": "kind", "enum_values": [str(i) for i in range(12)],
                   "distinct": 12}]
        self.assertEqual(len(gi.enum_fields(fields)), 1)

    def test_missing_enum_values_excluded(self):
        self.assertEqual(gi.enum_fields([{"name": "x", "distinct": 2}]), [])

    def test_none_fields_safe(self):
        self.assertEqual(gi.enum_fields(None), [])


class TestNumFields(unittest.TestCase):
    def test_numeric_only(self):
        fields = [{"name": "a", "detected_type": "integer"},
                  {"name": "b", "detected_type": "number"},
                  {"name": "c", "detected_type": "string"},
                  {"name": "d"}]
        self.assertEqual(gi.num_fields(fields), ["a", "b"])
        self.assertEqual(gi.num_fields(None), [])


class TestMenuEntry(unittest.TestCase):
    def test_required_vs_optional(self):
        entry = gi.menu_entry("probe", "desc",
                              {"must": {"type": "string"},
                               "opt": {"type": "integer", "__optional__": True}},
                              ["how many", "count"])
        self.assertEqual(entry["name"], "probe")
        self.assertEqual(entry["parameters"]["required"], ["must"])
        self.assertNotIn("__optional__", entry["parameters"]["properties"]["opt"])
        self.assertEqual(entry["triggers"], ["how many", "count"])
        self.assertEqual(entry["parameters"]["type"], "object")


if __name__ == "__main__":
    unittest.main()