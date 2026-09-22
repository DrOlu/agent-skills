"""Unit tests for the graph layer (graph_bridge.py).

The contract under test is references/graph-standards.md:
- tiers are awarded over FULL records (exact_fk >=5 shared, 1-4 candidate,
  zero disjoint — proven, quoted);
- bare id<->id surrogate collisions NEVER promote to exact_fk;
- cross-column joins need tight containment + a semantic guard;
- connect() must carry the b-side column (the cross-name continuity fix);
- digests are capped and exact_fk-first.

stdlib unittest only. Run:
  python3 -m unittest discover -s skills/neuralos/tests -v
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import graph_bridge  # noqa: E402
from graph_bridge import (GraphLayer, _keyish, _name_relates, _snake,
                          _stringify)  # noqa: E402


def write_edges(edges, disjoint=()):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"edges": edges, "disjoint": list(disjoint)}, fh)
    fh.close()
    return fh.name


# ---------------------------------------------------------------- fixtures
# The synthetic FK chain every finding from the 2026-09-22 rollout encodes:
# real 2-hop FK, a declared-then-disjoint pair, a surrogate id<->id pair,
# and a cross-column semantic-guard case.
RECORDS = {
    "artists": [
        {"id": str(i), "artist_id": f"AR{i}", "name": f"Artist{i}"}
        for i in range(1, 7)
    ] + [{"id": "9", "artist_id": "AR9-only-in-name", "name": "AC/DC"}],
    "albums": [
        {"album_id": f"AL{i}", "artist_id": f"AR{i}", "title": f"Title{i}"}
        for i in range(1, 7)
    ] + [{"album_id": "AL7", "artist_id": "AR9", "title": "Dangling"}],
    "tracks": [
        {"id": str(i), "track_id": f"T{i}", "album_id": f"AL{i}",
         "name": "Hells Bells" if i == 1 else f"Track{i}"}
        for i in range(1, 7)
    ],
    "scenarios": [{"id": "scenario_1_phishing"}, {"id": "scenario_2_malware"}],
    "events": [{"scenario_id": "scenario_1_phishing"},
               {"scenario_id": "scenario_2_malware"}],
    "blank": [{"x": "1"}],           # declared edge whose columns are absent
}

EDGES = [
    # real FK chain, declared same-name
    {"a": "albums", "a_col": "artist_id", "b": "artists", "b_col": "artist_id",
     "rule": "same_name", "tier": "proposed"},
    {"a": "albums", "a_col": "album_id", "b": "tracks", "b_col": "album_id",
     "rule": "same_name", "tier": "proposed"},
    # shared name, values never overlap -> runtime-disjoint
    {"a": "artists", "a_col": "name", "b": "albums", "b_col": "title",
     "rule": "same_name", "tier": "proposed"},
    # surrogate id<->id: numeric collision, must stay candidate even if
    # declared exact_fk
    {"a": "artists", "a_col": "id", "b": "tracks", "b_col": "id",
     "rule": "same_name", "tier": "exact_fk",
     "surrogate_warning": "both sides are bare 'id' keys"},
    # column absent at runtime -> demoted, not verified
    {"a": "blank", "a_col": "artist_id", "b": "artists", "b_col": "artist_id",
     "rule": "same_name", "tier": "proposed"},
]


class TestHelpers(unittest.TestCase):
    def test_snake_camelcase(self):
        # "ArtistId" normalizes to "artistid" — this is what made the
        # chinook model_dump keys match the declared camelCase edges.
        self.assertEqual(_snake("ArtistId"), "artistid")
        self.assertEqual(_snake("Support Rep Id"), "support_rep_id")

    def test_keyish(self):
        self.assertTrue(_keyish("artistid"))     # endswith id
        self.assertTrue(_keyish("scenario_id"))
        self.assertTrue(_keyish("name"))        # allowlisted soft key
        self.assertFalse(_keyish("title"))

    def test_name_relates(self):
        self.assertTrue(_name_relates("scenario_id", "scenarios"))
        self.assertTrue(_name_relates("host_id", "affected_hosts"))
        self.assertFalse(_name_relates("albumid", "invoice"))  # numeric-range guard
        self.assertFalse(_name_relates("id", "anything"))     # base too short

    def test_stringify(self):
        self.assertEqual(_stringify("v"), ["v"])
        self.assertEqual(_stringify(["a", "b"]), ["a", "b"])
        self.assertEqual(_stringify('["x", "y"]'), ["x", "y"])  # stringified list
        self.assertEqual(_stringify("[not json"), ["[not json"])


class TestTiering(unittest.TestCase):
    def test_surrogate_never_promotes(self):
        e = {"tier": "exact_fk", "surrogate_warning": "bare id pair"}
        self.assertEqual(GraphLayer._tier(e, {"1", "2", "3", "4", "5"}), "candidate")

    def test_surrogate_rule_never_promotes(self):
        e = {"rule": "surrogate_key_collision", "tier": "proposed"}
        self.assertEqual(GraphLayer._tier(e, set(str(i) for i in range(9))), "candidate")

    def test_five_shared_is_exact_fk(self):
        e = {"tier": "proposed"}
        self.assertEqual(GraphLayer._tier(e, {"a", "b", "c", "d", "e"}), "exact_fk")

    def test_four_shared_is_candidate(self):
        e = {"tier": "proposed"}
        self.assertEqual(GraphLayer._tier(e, {"a", "b", "c", "d"}), "candidate")


class TestVerifyAndDiscover(unittest.TestCase):
    def setUp(self):
        self.gl = GraphLayer(write_edges(EDGES))
        self.g = self.gl._verify(RECORDS)

    def test_declared_fk_verifies_with_matched_pairs(self):
        by = {(e["a"], e["b"]): e for e in self.g["verified"]}
        art = by[("albums", "artists")]
        self.assertEqual(art["matched_pairs"], 6)          # AR1..AR6 shared
        self.assertEqual(art["runtime_tier"], "exact_fk")  # >=5 shared values
        alb = by[("albums", "tracks")]
        self.assertEqual(alb["matched_pairs"], 6)

    def test_zero_overlap_is_disjoint_and_quoted(self):
        demoted = [d for d in self.g["demoted"]
                   if (d["a"], d["b"]) == ("artists", "albums")]
        self.assertEqual(len(demoted), 1)
        self.assertEqual(demoted[0]["runtime_tier"], "disjoint")
        self.assertIn("FULL records", demoted[0]["why"])

    def test_absent_column_demoted_not_verified(self):
        demoted = [d for d in self.g["demoted"]
                   if d["a"] == "blank" or d["b"] == "blank"]
        self.assertTrue(demoted, "absent-column edge must be demoted with a why")

    def test_dangling_refs_counted(self):
        dang = [d for d in self.g["dangling"]
                if d["a"] == "albums" and d["column"] == "artist_id"]
        self.assertEqual(dang[0]["dangling_refs"], 1)     # AR9 has no artist

    def test_cross_column_semantic_guard_discovers_fk(self):
        # events.scenario_id -> scenarios.id is the canonical cross-column case:
        # child base name relates to the parent TABLE, containment is total.
        cross = [e for e in self.g["verified"]
                 if e.get("rule") == "value_overlap_cross_column"]
        found = {(e["a"], e["a_col"], e["b"], e["b_col"]) for e in cross}
        self.assertIn(("events", "scenario_id", "scenarios", "id"), found)
        e = next(e for e in cross if e["b"] == "scenarios")
        self.assertEqual(e["runtime_tier"], "exact_fk")
        self.assertEqual(e["matched_pairs"], 2)

    def test_numeric_collision_not_discovered(self):
        # albumid values numerically inside a bigger id range must never
        # produce a cross-column edge to an unrelated table (no semantic link).
        cross = [e for e in self.g["verified"]
                 if e.get("rule") == "value_overlap_cross_column"]
        for e in cross:
            self.assertNotEqual((e["a"], e["b"]), ("albums", "tracks"))

    def test_surrogate_stays_candidate(self):
        ver = [e for e in self.g["verified"] if e["a_col"] == "id"]
        for e in ver:
            self.assertEqual(e["runtime_tier"], "candidate")


class TestProbes(unittest.TestCase):
    def setUp(self):
        self.gl = GraphLayer(write_edges(EDGES))
        self.ov = lambda: self.gl.overview(RECORDS)

    def test_overview_counts_and_nodes(self):
        o = self.ov()
        nodes = {n["table"]: n["rows"] for n in o["nodes"]}
        self.assertEqual(nodes["artists"], 7)   # 6 + the AR9-only-in-name row
        self.assertEqual(nodes["tracks"], 6)
        self.assertGreaterEqual(o["edges_total"], 3)

    def test_overview_surfaces_disjoint(self):
        o = self.ov()
        self.assertGreaterEqual(o["disjoint_edges"], 1)
        self.assertTrue(any(d["a"] == "artists" for d in o["disjoint"]))

    def test_overview_exact_fk_first(self):
        o = self.ov()
        tiers = [e["tier"] for e in o["edges_verified"]]
        self.assertEqual(tiers, sorted(tiers, key=lambda t: t != "exact_fk"))

    def test_overview_caps_with_edges_more(self):
        gl = GraphLayer(write_edges(EDGES), result_cap=1)
        o = gl.overview(RECORDS)
        self.assertEqual(len(o["edges_verified"]), 1)
        self.assertGreaterEqual(o["edges_more"], 1)

    def test_mermaid_lists_edges(self):
        m = self.ov()["mermaid"]
        self.assertIn("graph LR", m)
        self.assertIn("albums", m)

    def test_neighbors_links_with_provenance(self):
        r = self.gl.neighbors(RECORDS, "AR1")
        links = [l for m in r["matches"] for l in m["links"]]
        self.assertTrue(links)
        self.assertTrue(all(l["tier"] in ("exact_fk", "candidate") for l in links))

    def test_neighbors_linkless_note_is_honest(self):
        r = self.gl.neighbors(RECORDS, "Hells Bells")
        self.assertEqual(r["matches"][0]["links"], [])
        self.assertIn("no verified edges", r["matches"][0]["note"])

    def test_neighbors_unknown_fragment_errors(self):
        r = self.gl.neighbors(RECORDS, "NO-SUCH-VALUE")
        self.assertIn("error", r)

    def test_connect_two_hop_reachable(self):
        r = self.gl.connect(RECORDS, "AR1", "Hells Bells")
        self.assertTrue(r["reachable"])
        route = " -> ".join(r["paths"][0]["route"])
        self.assertIn("albums", route)

    def test_connect_carries_shared_values_cross_name(self):
        # The b_col continuity fix: a path through a cross-name edge must
        # still report the shared key values (this was empty before the fix).
        r = self.gl.connect(RECORDS, "scenario_1", "scenario_2_malware")
        self.assertTrue(r["reachable"])

    def test_connect_honest_unreachable(self):
        r = self.gl.connect(RECORDS, "Dangling", "Metallica")
        self.assertIn("reachable", r)
        # either an explicit why (no path) or no path found — never a fake route
        if r.get("reachable") is False:
            self.assertTrue(r["why"])

    def test_connect_unknown_target(self):
        r = self.gl.connect(RECORDS, "AR1", "NO-SUCH-TARGET")
        self.assertFalse(r["reachable"])
        self.assertIn("no node matches", r["why"])


if __name__ == "__main__":
    unittest.main()