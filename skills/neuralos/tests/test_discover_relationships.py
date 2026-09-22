"""Unit tests for discover_relationships.py — the graph-layer proposer.

Contract: discovery PROPOSES by name only (runtime verifies); bare id<->id
pairs carry a surrogate warning; camelCase normalizes; disjoint findings are
runtime-computed (the proposer never asserts them from samples).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import discover_relationships as dr  # noqa: E402


def run_discovery(tables):
    profile = {"profiled_at": "test", "source": {"kind": "database",
                                                  "tables": tables}}
    p = os.path.join(tempfile.mkdtemp(), "profile.json")
    json.dump(profile, open(p, "w"))
    out = os.path.join(os.path.dirname(p), "graph_edges.json")
    # call main() with argv patched
    old_argv = sys.argv
    sys.argv = ["discover_relationships.py", "--profile", p, "--out", out]
    try:
        dr.main()
    finally:
        sys.argv = old_argv
    return json.load(open(out))


def table(name, columns, rows=10, sample_records=None):
    return {"name": name, "db_row_count": rows, "columns": columns,
            "sample_records": sample_records or []}


class TestSnake(unittest.TestCase):
    def test_camelcase_collapses(self):
        self.assertEqual(dr.snake("ArtistId"), "artistid")

    def test_spaces_to_underscores(self):
        self.assertEqual(dr.snake("First Name"), "first_name")


class TestKeyish(unittest.TestCase):
    def test_keyish(self):
        for col in ("artist_id", "txn_id", "account_id", "name", "email",
                    "hostname", "zone", "id", "albumid"):
            self.assertTrue(dr._keyish(dr.snake(col)), col)
        self.assertFalse(dr._keyish("title"))


class TestProposals(unittest.TestCase):
    def setUp(self):
        self.result = run_discovery([
            table("Artist", [{"name": "ArtistId", "sample_values": [1, 2]},
                             {"name": "Name", "sample_values": ["a", "b"]}]),
            table("Album", [{"name": "ArtistId", "sample_values": [1, 2, 3]},
                            {"name": "Title", "sample_values": ["x", "y"]}]),
            table("Unrelated", [{"name": "Title", "sample_values": ["q"]}]),
        ])

    def test_same_name_id_pair_proposed(self):
        pairs = {(e["a"], e["b"], e["a_col"], e["b_col"])
                 for e in self.result["edges"]}
        self.assertIn(("Artist", "Album", "ArtistId", "ArtistId"), pairs)

    def test_surrogate_flagged_never_exact(self):
        for e in self.result["edges"]:
            self.assertNotEqual(e["tier"], "exact_fk")  # proposer never awards
            self.assertIn("runtime verifies", e["evidence"])

    def test_non_keyish_same_name_skipped(self):
        # Title appears in two tables but is not keyish -> no proposal
        self.assertFalse(any(e["a_col"] == "Title" or e["b_col"] == "Title"
                             for e in self.result["edges"]))

    def test_disjoint_not_asserted_from_samples(self):
        self.assertEqual(self.result["disjoint"], [])
        self.assertIn("runtime", self.result["note"])

    def test_nodes_carry_row_counts(self):
        nodes = {n["table"]: n["rows"] for n in self.result["nodes"]}
        self.assertEqual(nodes, {"Artist": 10, "Album": 10, "Unrelated": 10})


class TestSurrogateId(unittest.TestCase):
    def test_bare_id_pair_gets_warning(self):
        result = run_discovery([
            table("events", [{"name": "id", "sample_values": [1, 2]}]),
            table("hosts", [{"name": "id", "sample_values": [1, 2]}]),
        ])
        self.assertEqual(len(result["edges"]), 1)
        e = result["edges"][0]
        self.assertEqual(e["rule"], "surrogate_key_collision")
        self.assertIn("bare 'id'", e["surrogate_warning"])


if __name__ == "__main__":
    unittest.main()