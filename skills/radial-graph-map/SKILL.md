---
name: radial-graph-map
description: >
  Render any dataset's relationship graph as a large, readable SVG + PNG with a
  provably clean layout — zero node overlaps, zero edges passing over nodes,
  zero label collisions, minimized edge crossings, every connection labeled.
  Use this skill whenever the user wants to map relationships, connections,
  networks, org charts, entity graphs, "who is connected to whom", fraud or
  investigation maps, knowledge graphs, system topologies, supply chains,
  social networks, or any nodes-and-edges picture — even if they just say
  "graph this", "visualize these connections", or "map the relationships" in
  any dataset, from a 6-person team to a 50+-node forensic dossier.
---

# Radial Graph Map

Turn a relationship dataset into a publication-grade radial graph. The engine
(`scripts/radial_graph.py`) uses a **provable radial tree layout**: BFS spanning
tree as radial spokes inside convex wedges, non-tree edges as constant-radius
arcs in per-source concentric bands outside every node, and collision-checked
label placement. The bundled test suite verifies the guarantees on every render
shape — run it before delivering (see Verification).

## Workflow

1. **Extract** — read the source data (CSV, SQLite, JSON, emails, documents,
   instance probes, whatever it is) and build a graph spec: entities as nodes,
   relationships as edges. Follow `references/spec-format.md` — it has the full
   JSON schema plus copy-paste extraction recipes (SQL, pandas, plain text).
2. **Write the spec** as a JSON file. Assign each node a semantic `type`
   (person, entity, document, event, money, news, legal, group, place, product,
   or your own via `types`) and each edge a `style` + short `label`. Every edge
   MUST have a label — unlabeled connections are the #1 readability failure.
3. **Render**:
   ```bash
   python3 scripts/radial_graph.py --spec graph.json --svg out.svg --png out.png
   ```
   It prints node/edge counts, canvas size, ring count, scale factor, and the
   achieved (minimized) chord-crossing count. Deterministic — same spec, same
   picture (seeded annealing, default seed 4242).
4. **Verify** — run the invariant suite from the skill directory:
   ```bash
   cd tests && python3 -m unittest test_invariants
   ```
   If you added a new example spec, add it to `EXAMPLES` in
   `tests/test_invariants.py` so its invariants are locked too.
5. **Deliver** the SVG (crisp at any zoom, hover tooltips carry provenance)
   and the PNG (raster fallback). Report the metrics line so the user can see
   the layout quality.

## Choosing what to include (from messy data)

- **Pick a focal node** for `root` — the person/entity the map is "about".
  Omit `root` and the engine picks the highest-degree node.
- **Layer node types**: people, organizations, documents, events, money
  amounts, places. The visual color coding is what makes a complex map
  scannable.
- **Edge styles carry meaning**: `struct` (verified/structural), `co`
  (co-mention/co-occurrence, dashed), `green` (the key directive/action),
  `money`, `legal`, `spouse`, `news`, `meet`, `solid`/`dash` (generic).
- **Put evidence in `tip`**: each node's hover tooltip should carry the
  provenance (source, date, verbatim quote). A graph without provenance is a
  cartoon; with it, it's evidence.
- **`subs` are the properties**: 1–3 short lines under each node title
  (role, dates, key numbers). They make the map self-contained.

## Scale guidance

| Dataset | What to do |
|---|---|
| ≤ 15 nodes | Render everything. |
| 16–45 nodes | Render everything; keep edge labels ≤ ~30 chars (the engine wraps on `·` and `;`). |
| 46–90 nodes | Curate first: keep the highest-signal edges (aim ≤ ~90 edges). Every extra edge costs label space. |
| > 90 nodes | Split into thematic maps (per cluster, per timeframe) sharing a root, or rank edges and map the top N with a note about what was cut. |

The engine places ONE label per edge and grows the canvas as needed — complexity
is bounded by label real estate, not node count.

## The algorithm (one paragraph)

BFS from the root builds a spanning tree (orphans hang off the root on ring 1).
Leaves are placed on circular slots and their order is annealed (deterministic,
seeded) to minimize chord interleavings and inner-ring crowding; subtree
contiguity is then restored so every parent sits inside its own wedge. Nodes
sit on depth rings whose radii grow until same-depth neighbors tangentially fit
(circular pairwise check, per ring), with radial monotonicity enforced between
rings. Tree edges are straight radial spokes (they cannot leave their convex
wedge, so they cannot cross other spokes or pass over nodes). Every non-tree
edge becomes a constant-radius polyline in a band reserved for its source node,
outside all node envelopes — bands never intersect. Labels are placed by a
collision-checked candidate search (chord labels on their band; spoke labels
along the edge with offsets). Finally the whole validated geometry is scaled
uniformly by K — a zoom that preserves every separation.

Full details, invariants, and the proofs-by-construction:
`references/algorithm.md`.

## When the output needs iteration

- **Too sparse / rings feel far apart** — that's the cost of the guarantees;
  don't hack the constants, prune edges or shorten labels instead.
- **A chord label sits oddly** — shorten the label; band labels are centered
  on the band midpoint.
- **Want a different emphasis** — change `root`; the entire wedge structure
  reorganizes around it. Try the focal suspect, the flagship product, the CEO.
- **Custom node types** — add `"types": {"mytype": ["#fill", "#stroke"]}` at
  spec top level; unknown types fall back to a neutral gray.

## Requirements

Python 3.10+ stdlib only. PNG conversion uses macOS `qlmanage` when available;
without it the SVG is still written (PNG step prints a skip note). Nothing to
install.
