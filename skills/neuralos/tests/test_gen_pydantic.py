"""Unit tests for gen_pydantic.py — Phase-2 model emission.

Pins the #1 generated-model failure (aliases: rows arrive keyed by the
SOURCE names, so a differing snake name must carry Field(alias=...)), the
nullable Optional wrap (Pydantic v2 rejects explicit nulls without it), and
the enum/Literal capping rules.
"""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import gen_pydantic as gp  # noqa: E402


class TestSnake(unittest.TestCase):
    def test_snake(self):
        self.assertEqual(gp._snake("ArtistId"), "artistid")
        self.assertEqual(gp._snake("First Name"), "first_name")
        self.assertEqual(gp._snake("@timestamp"), "at_timestamp")
        self.assertEqual(gp._snake("9lives"), "f_9lives")  # leading digit guard


class TestFieldLine(unittest.TestCase):
    def test_alias_emitted_when_name_differs(self):
        _, line = gp.field_line("ArtistId",
                                {"python_type": "str", "detected_type": "string",
                                 "nullable": False, "min_len": 1, "max_len": 5})
        self.assertIn('alias="ArtistId"', line)
        self.assertNotIn("default=None", line)

    def test_no_alias_when_names_match(self):
        _, line = gp.field_line("title",
                                {"python_type": "str", "detected_type": "string",
                                 "nullable": False, "min_len": 1, "max_len": 5})
        self.assertNotIn("alias=", line)

    def test_nullable_wraps_optional_and_defaults(self):
        _, line = gp.field_line("x",
                                {"python_type": "str", "detected_type": "string",
                                 "nullable": True, "min_len": 1, "max_len": 5})
        self.assertIn("Optional[str]", line)
        self.assertIn("default=None", line)

    def test_numeric_bounds(self):
        name, line = gp.field_line("n",
                                   {"python_type": "int", "detected_type": "integer",
                                    "nullable": False, "min": 1, "max": 9})
        self.assertIn("ge=1", line)
        self.assertIn("le=9", line)

    def test_enum_becomes_literal(self):
        _, line = gp.field_line("kind",
                                {"python_type": "Literal", "detected_type": "string",
                                 "nullable": False,
                                 "enum_values": ["a", "b"],
                                 "distinct": 2, "sample_count": 4})
        self.assertIn("Literal[\"a\", \"b\"]", line)

    def test_oversized_enum_falls_back_to_str(self):
        big = "x" * 200
        _, line = gp.field_line("blob",
                                {"python_type": "Literal", "detected_type": "string",
                                 "nullable": False,
                                 "enum_values": [big, big + "y"],
                                 "distinct": 2, "sample_count": 4,
                                 "sample_values": [big]})
        self.assertIn(": str", line)
        self.assertNotIn("Literal[", line)

    def test_regex_wins_over_bounds(self):
        _, line = gp.field_line("ip",
                                {"python_type": "str", "detected_type": "string",
                                 "nullable": False, "regex": r"\d+\.\d+\.\d+\.\d+"})
        self.assertIn("pattern=r\"", line)
        self.assertNotIn("ge=", line)


class TestModelFor(unittest.TestCase):
    def test_class_and_config(self):
        out = gp.model_for("Invoice", [
            {"name": "Total", "python_type": "float", "detected_type": "number",
             "nullable": False, "min": 0.99, "max": 5.99},
        ], "3 rows in source.")
        self.assertIn("class Invoice(BaseModel):", out)
        self.assertIn('extra="forbid", populate_by_name=True', out)

    def test_datetime_validator_emitted(self):
        out = gp.model_for("Ev", [
            {"name": "ts", "python_type": "datetime", "detected_type": "datetime",
             "nullable": False},
        ], "1 row.")
        self.assertIn('@field_validator("ts", mode="before")', out)
        self.assertIn("def _parse_datetime", out)

    def test_no_validator_without_datetime_fields(self):
        out = gp.model_for("T", [
            {"name": "x", "python_type": "str", "detected_type": "string",
             "nullable": False, "min_len": 1, "max_len": 2},
        ], "1 row.")
        self.assertNotIn("field_validator", out)

    def test_duplicate_field_names_deduped(self):
        out = gp.model_for("Dup", [
            {"name": "Name", "python_type": "str", "detected_type": "string",
             "nullable": False, "min_len": 1, "max_len": 4},
            {"name": "name", "python_type": "str", "detected_type": "string",
             "nullable": False, "min_len": 1, "max_len": 4},
        ], "1 row.")
        self.assertIn("name: ", out)
        self.assertIn("name_: ", out)

    def test_empty_fields_emit_pass(self):
        out = gp.model_for("Empty", [], "0 rows.")
        self.assertIn("pass", out)

    def test_name_collision_appends_model(self):
        used = {"Record"}
        out = gp.model_for("Record", [], "x", used_names=used)
        self.assertIn("class RecordModel(BaseModel):", out)


class TestDateTimeValidator(unittest.TestCase):
    def test_empty_names_empty_string(self):
        self.assertEqual(gp.datetime_validator([]), "")

    def test_joined_names(self):
        v = gp.datetime_validator(["a", "b"])
        self.assertIn('"a", "b"', v)


@unittest.skipUnless(importlib.util.find_spec("pydantic"),
                   "pydantic not installed for this interpreter")
class TestGeneratedModelRoundTrip(unittest.TestCase):
    """The emitted model must actually accept source-keyed rows."""
    def test_alias_round_trip(self):
        fields = [
            {"name": "ArtistId", "python_type": "int", "detected_type": "integer",
             "nullable": False, "min": 1, "max": 5},
            {"name": "Name", "python_type": "str", "detected_type": "string",
             "nullable": True, "min_len": 1, "max_len": 40},
        ]
        src = gp.model_for("Artist", fields, "2 rows in source.")
        ns = {}
        prelude = ("from pydantic import BaseModel, Field, field_validator, "
                   "ConfigDict\n"
                   "from typing import Optional, Literal\n"
                   "from datetime import datetime\n")
        exec(compile(prelude, "prelude.py", "exec"), ns)
        exec(compile(src, "models_test.py", "exec"), ns)
        Artist = ns["Artist"]
        # rows arrive keyed by the SOURCE column names
        row = Artist(**{"ArtistId": 1, "Name": "AC/DC"})
        self.assertEqual(row.name, "AC/DC")
        self.assertEqual(row.artistid, 1)
        # alias round-trip: source keys work, snake keys too (populate_by_name)
        row2 = Artist(**{"artistid": 2, "name": "Metallica"})
        self.assertEqual(row2.artistid, 2)


if __name__ == "__main__":
    unittest.main()