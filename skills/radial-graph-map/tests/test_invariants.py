#!/usr/bin/env python3
"""Invariant suite for radial_graph.py — the guarantees that make the layout
'provably clean'. Runs against the shipped example specs AND seeded random
specs, so any future edit that breaks a guarantee fails here.

Run:
  cd <skill-dir>/tests
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m unittest test_invariants -v
"""
import json
import math
import os
import random
import sys
import unittest
import xml.dom.minidom as minidom

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import radial_graph as rg  # noqa: E402

EXAMPLES = [
    os.path.join(SKILL, "examples", "fraud-investigation.json"),
    os.path.join(SKILL, "examples", "simple-org-chart.json"),
]


def load_spec(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def boxes_of(layout):
    """Node bounding boxes: id -> (x0, y0, w, h)."""
    return {u: (p[0] - layout["dims"][u][0] / 2, p[1] - layout["dims"][u][1] / 2,
                layout["dims"][u][0], layout["dims"][u][1])
            for u, p in layout["pos"].items()}


def rects_overlap(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or
                a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def seg_hits_rect(x0, y0, x1, y1, rx, ry, rw, rh):
    return rg.seg_recs_intersect(x0, y0, x1, y1, rx, ry, rw, rh) is not None


class InvariantChecks:
    """Mixin: every check takes a loaded (spec, layout) pair."""

    def check_all_nodes_positioned(self, spec, layout):
        ids = {n["id"] for n in spec["nodes"]}
        self.assertEqual(set(layout["pos"]), ids)
        for u, p in layout["pos"].items():
            self.assertTrue(math.isfinite(p[0]) and math.isfinite(p[1]), u)

    def check_no_node_overlaps(self, spec, layout):
        bx = boxes_of(layout)
        ids = sorted(bx)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                self.assertFalse(rects_overlap(bx[a], bx[b]), f"{a} X {b}")

    def check_nodes_within_canvas(self, spec, layout):
        W, H = layout["W"], layout["H"]
        for u, b in boxes_of(layout).items():
            self.assertGreaterEqual(b[0], 0, u)
            self.assertGreaterEqual(b[1], 0, u)
            self.assertLessEqual(b[0] + b[2], W, u)
            self.assertLessEqual(b[1] + b[3], H, u)

    def check_tree_spans_all_nodes(self, spec, layout):
        edges = layout["live_edges"]
        adj = {u: [] for u in layout["pos"]}
        for ei in layout["tree"]:
            a, b = edges[ei][0], edges[ei][1]
            adj[a].append(b)
            adj[b].append(a)
        seen, stack = {layout["root"]}, [layout["root"]]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        # nodes with no incident edges are orphans: the engine attaches them
        # to the root synthetically (ring 1) — no spec edge exists to traverse
        touched = {e["source"] for e in spec["edges"]} | {e["target"] for e in spec["edges"]}
        orphans = {n["id"] for n in spec["nodes"]} - touched
        self.assertEqual(seen | orphans, set(layout["pos"]),
                         "spanning tree does not reach every node")

    def check_tree_edges_pass_over_no_node(self, spec, layout):
        pos, dims, bx = layout["pos"], layout["dims"], boxes_of(layout)
        bad = []
        for ei in layout["tree"]:
            a, b = layout["live_edges"][ei][0], layout["live_edges"][ei][1]
            ax, ay = pos[a][0] + dims[a][0] / 2, pos[a][1] + dims[a][1] / 2
            x1, y1 = pos[b][0] + dims[b][0] / 2, pos[b][1] + dims[b][1] / 2
            for nid, (rx, ry, rw, rh) in bx.items():
                if nid in (a, b):
                    continue
                if seg_hits_rect(ax, ay, x1, y1, rx, ry, rw, rh):
                    bad.append((a, b, nid))
        self.assertEqual(bad, [])

    def check_chords_pass_over_no_node(self, spec, layout):
        bx = boxes_of(layout)
        bad = []
        for ei, poly in layout["chord_geom"].items():
            a, b = layout["live_edges"][ei][0], layout["live_edges"][ei][1]
            for px, py in poly:
                for nid, (rx, ry, rw, rh) in bx.items():
                    if nid in (a, b):
                        continue
                    if rx <= px <= rx + rw and ry <= py <= ry + rh:
                        bad.append((a, b, nid))
        self.assertEqual(bad, [])

    def check_chords_within_canvas(self, spec, layout):
        W, H = layout["W"], layout["H"]
        for ei, poly in layout["chord_geom"].items():
            for px, py in poly:
                self.assertGreaterEqual(px, 0, f"edge {ei}")
                self.assertGreaterEqual(py, 0, f"edge {ei}")
                self.assertLessEqual(px, W, f"edge {ei}")
                self.assertLessEqual(py, H, f"edge {ei}")

    def check_labels(self, spec, layout):
        """One label per edge; no label-label or label-node collisions; in-canvas."""
        labs = layout["labels"]
        self.assertEqual(len(labs), len(layout["live_edges"]))
        recs = list(labs.values())
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                self.assertFalse(rects_overlap(recs[i][:4], recs[j][:4]),
                                 f"labels {i} and {j} overlap")
        bx = boxes_of(layout)
        for ei, rec in labs.items():
            a, b = layout["live_edges"][ei][0], layout["live_edges"][ei][1]
            for nid, nrec in bx.items():
                if nid in (a, b):
                    continue
                self.assertFalse(rects_overlap(rec[:4], nrec),
                                 f"label {ei} overlaps node {nid}")
        W, H = layout["W"], layout["H"]
        for ei, rec in labs.items():
            self.assertGreaterEqual(rec[0], 0, f"label {ei}")
            self.assertGreaterEqual(rec[1], 0, f"label {ei}")
            self.assertLessEqual(rec[0] + rec[2], W, f"label {ei}")
            self.assertLessEqual(rec[1] + rec[3], H, f"label {ei}")

    def check_svg(self, spec, layout, svg):
        dom = minidom.parseString(svg)
        texts = " ".join(t.firstChild.nodeValue
                         for t in dom.getElementsByTagName("text") if t.firstChild)
        self.assertIn("LEGEND", texts)
        for n in spec["nodes"]:
            self.assertIn(n.get("label", n["id"]), texts,
                          f"missing node label {n['id']}")


class SpecChecks:
    """Mixin: spec-quality checks the skill instructs authors to satisfy."""

    def check_spec_quality(self, spec):
        ids = [n["id"] for n in spec["nodes"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate node ids")
        idset = set(ids)
        for e in spec["edges"]:
            self.assertIn(e["source"], idset, e)
            self.assertIn(e["target"], idset, e)
            self.assertTrue(e.get("label") and len(e["label"]) >= 3,
                            f"unlabeled/short edge {e}")
            self.assertIn(e.get("style", "struct"), rg.STYLES)
        for n in spec["nodes"]:
            self.assertIn(n.get("type", "other"), rg.PALETTE)


def run_all(checks, spec, layout):
    checks.check_all_nodes_positioned(spec, layout)
    checks.check_no_node_overlaps(spec, layout)
    checks.check_nodes_within_canvas(spec, layout)
    checks.check_tree_spans_all_nodes(spec, layout)
    checks.check_tree_edges_pass_over_no_node(spec, layout)
    checks.check_chords_pass_over_no_node(spec, layout)
    checks.check_chords_within_canvas(spec, layout)
    checks.check_labels(spec, layout)


def random_spec(seed, n=20, m=34):
    rr = random.Random(seed)
    nodes = [{"id": f"n{i}", "type": rr.choice(list(rg.PALETTE)),
              "label": f"NODE {i} " + "X" * rr.randint(0, 8),
              "subs": [f"property {i}.{k}" for k in range(rr.randint(0, 3))]}
             for i in range(n)]
    ids = [nd["id"] for nd in nodes]
    edges, seen = [], set()
    while len(edges) < m:
        a, b = rr.choice(ids), rr.choice(ids)
        if a == b or (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))
        edges.append({"source": a, "target": b,
                      "label": f"relationship {len(edges)}",
                      "style": rr.choice(list(rg.STYLES))})
    return {"title": f"random {seed}", "nodes": nodes, "edges": edges}


class TestShippedExamples(InvariantChecks, SpecChecks, unittest.TestCase):

    def test_fraud_investigation_full_invariants(self):
        spec = load_spec(EXAMPLES[0])
        layout = rg.compute_layout(spec)
        self.check_spec_quality(spec)
        run_all(self, spec, layout)
        self.check_svg(spec, layout, rg.render_svg(layout, spec))

    def test_org_chart_full_invariants(self):
        spec = load_spec(EXAMPLES[1])
        layout = rg.compute_layout(spec)
        self.check_spec_quality(spec)
        run_all(self, spec, layout)
        self.check_svg(spec, layout, rg.render_svg(layout, spec))
        # simple datasets should achieve zero chord crossings outright
        self.assertEqual(layout["chord_crossings"], 0)

    def test_example_artifacts_exist(self):
        for name in ("fraud-investigation", "simple-org-chart"):
            svg = os.path.join(SKILL, "examples", "out", f"{name}.svg")
            png = os.path.join(SKILL, "examples", "out", f"{name}.png")
            minidom.parse(svg)
            with open(png, "rb") as fh:
                self.assertTrue(fh.read(8).startswith(b"\x89PNG"), name)
            self.assertGreater(os.path.getsize(png), 100_000, name)


class TestEngineProperties(InvariantChecks, unittest.TestCase):

    def test_seeded_random_specs_hold_invariants(self):
        for seed in (1, 7, 42, 4242):
            with self.subTest(seed=seed):
                spec = random_spec(seed)
                run_all(self, spec, rg.compute_layout(spec))

    def test_layout_is_deterministic(self):
        spec = load_spec(EXAMPLES[0])
        l1, l2 = rg.compute_layout(spec), rg.compute_layout(spec)
        self.assertEqual(l1["pos"], l2["pos"])
        self.assertEqual(l1["rings"], l2["rings"])
        self.assertEqual(l1["chord_crossings"], l2["chord_crossings"])

    def test_auto_root_picks_highest_degree(self):
        spec = {"title": "t",
                "nodes": [{"id": c, "type": "person", "label": c}
                          for c in "abcde"],
                "edges": [{"source": "a", "target": b, "label": "knows"}
                          for b in "bcde"]}
        self.assertEqual(rg.compute_layout(spec)["root"], "a")

    def test_orphans_get_ring1_slots_not_center(self):
        spec = {"title": "t",
                "nodes": [{"id": "x", "type": "person", "label": "X"}] +
                         [{"id": f"o{i}", "type": "other", "label": f"O{i}"}
                          for i in range(5)],
                "edges": [{"source": "o3", "target": "x", "label": "knows"}]}
        layout = rg.compute_layout(spec)
        run_all(self, spec, layout)
        # o3 owns the only edge → becomes root; x is its tree child; the rest
        # are orphans → must sit on ring 1 (not at the center), distinct angles
        self.assertEqual(layout["root"], "o3")
        r1 = layout["rings"][1]
        angs = []
        for oid in ("o0", "o1", "o2", "o4"):
            p = layout["pos"][oid]
            r = math.hypot(p[0] - layout["CX"], p[1] - layout["CY"])
            self.assertAlmostEqual(r, r1, delta=r1 * 0.02, msg=oid)
            angs.append(math.atan2(p[1] - layout["CY"], p[0] - layout["CX"]))
        gaps = [b - a for a, b in zip(sorted(angs), sorted(angs)[1:])]
        self.assertTrue(all(g > 0.05 for g in gaps), "orphan angles collide")

    def test_empty_spec_raises(self):
        with self.assertRaises(Exception):
            rg.compute_layout({"title": "t", "nodes": [], "edges": []})

    def test_metrics_reported(self):
        spec = load_spec(EXAMPLES[0])
        layout = rg.compute_layout(spec)
        self.assertIsInstance(layout["chord_crossings"], int)
        self.assertGreaterEqual(layout["chord_crossings"], 0)
        self.assertIsInstance(layout["inner_crowding_score"], int)
        self.assertEqual(layout["node_count"], len(spec["nodes"]))
        self.assertEqual(layout["edge_count"], len(spec["edges"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
