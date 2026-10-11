# The Radial Tree Layout Algorithm

This document specifies exactly how `scripts/radial_graph.py` turns a graph
spec into a provably clean rendering, and why each guarantee holds. The
invariants are enforced by `tests/test_invariants.py` — if you change the
engine, the suite tells you immediately if a guarantee broke.

## Table of contents
1. [Guarantees](#guarantees)
2. [Pipeline overview](#pipeline-overview)
3. [Stage details](#stage-details)
   - [Spanning tree and orphans](#1-spanning-tree-and-orphans)
   - [Leaf slots and annealing](#2-leaf-slots-and-annealing)
   - [Subtree contiguity restoration](#3-subtree-contiguity-restoration)
   - [Angles: arc midpoints, one convention](#4-angles-arc-midpoints-one-convention)
   - [Depth rings and tangential growth](#5-depth-rings-and-tangential-growth)
   - [Radial monotonicity clamp](#6-radial-monotonicity-clamp)
   - [K zoom](#7-k-zoom)
   - [Chord bands](#8-chord-bands)
   - [Label placement](#9-label-placement)
4. [Why each guarantee is true](#why-each-guarantee-is-true)
5. [Known approximation](#known-approximation)
6. [Failure modes the design eliminates](#failure-modes-the-design-eliminates)

## Guarantees

A rendering produced by this engine (and verified by the test suite) contains:

| # | Invariant | Bounded by |
|---|---|---|
| 1 | No two node boxes overlap | ring growth + radial clamp |
| 2 | No tree edge passes over any node | convex-wedge argument |
| 3 | No chord edge passes over any node | bands outside all envelopes |
| 4 | No label–label or label–node collision | collision-checked placement |
| 5 | Everything inside the canvas | measured extent + band reserve |
| 6 | Every node reachable from root | BFS + orphan attachment |
| 7 | Chord–chord crossings minimized | seeded annealing (deterministic) |
| 8 | Determinism | fixed seed, no wall-clock input |

Invariants 1–6 are hard (structure); 7 is an optimization with a locked,
reproducible result; 8 makes reruns byte-identical.

## Pipeline overview

```
spec ─▶ BFS spanning tree ─▶ leaf slots ─▶ seeded annealing (crossings,
crowding) ─▶ contiguity restore ─▶ arc-midpoint angles ─▶ ring growth
(tangential fit) ─▶ radial clamp ─▶ K zoom ─▶ chord bands ─▶ label search
─▶ SVG (+ PNG)
```

Angles live in [0, 2π) end-to-end. Everything before the K zoom is in "base
units" with K = 1; the zoom multiplies geometry uniformly.

## Stage details

### 1. Spanning tree and orphans
BFS from `root` (spec-given or highest-degree node) over the undirected edge
multiset. First discovery of each node fixes its parent — that edge is a *tree
edge*; all others are *chords*. Nodes with no incident edge (orphans) get a
synthetic `(root, -1)` parent: they are appended to `kids[root]`, so they
become ring-1 leaves with real angular slots instead of collapsing onto the
center. No synthetic edge is drawn — orphans simply sit on ring 1.

### 2. Leaf slots and annealing
Leaves (DFS from root, orphans included) get slots `(i + 0.5) · 2π/L`. A
seeded simulated annealer (`Random(seed)`, T from 300 → 1, 8000 steps, local
swaps of ±1..±4 slots) minimizes:

- **interleave count** — pairs of chords whose endpoint angles separate each
  other (interval-crossing test);
- **inner-ring crowding** (+300 per violation) — same-ring neighbor pairs
  whose angular gap is too small for their widths at ring-1 radius;
- **spoke-block** (+200) — a foreign ring-1 leaf sitting inside an internal
  node's leaf-span.

### 3. Subtree contiguity restoration
Annealing moves individual leaves and can scatter a subtree's leaves around
the circle, which would break the wedge argument. Fix: for every internal
node, sort its children by the circular mean of their subtree leaves' annealed
slots; then re-emit leaves depth-first in that rotated order and assign fresh
slots. Each subtree now owns one contiguous arc, and the arrangement still
mirrors the annealed structure (children point where annealing put them).

### 4. Angles: arc midpoints, one convention
`angle_of(u)` = u's slot for leaves; for internal nodes, the **midpoint of
their subtree's leaf arc** (handling the 2π wrap when the arc exceeds π).
Two deliberate choices:

- **Arc midpoint, not vector resultant.** `atan2(Σsin, Σcos)` degenerates when
  a subtree's leaves are near-symmetric about π (sums → 0 → atan2(0,0)), and
  can point *outside* the subtree's own arc. The midpoint always lies inside
  the arc, hence inside the wedge.
- **One convention.** Leaf slots are [0, 2π); raw `atan2` returns (−π, π].
  Mixing them scrambles circular sorts and gap tests — a node at 5.18 rad and
  one at −1.10 rad are 0.31 rad apart, but a naive sort treats them as
  polar opposites. Normalizing to [0, 2π) everywhere fixes sorting, gap
  tests, and the interleave objective.

### 5. Depth rings and tangential growth
Ring radii start at `780 · 1.45^(d−1)` (deep chains fold onto ring 4).
Positions are polar `(ring[depth], angle_of)`. Then a growth loop (≤14
iterations): for **each ring independently**, take its nodes in circular
angular order — *including the wraparound pair across the 2π seam* — and
require, for every adjacent pair, `ring ≥ (w1/2 + w2/2 + 44) / Δθ`. If any
ring violates, grow it by `max(1.12, min(need/ring, 1.5))` and repeat. This
guarantees same-ring neighbors have enough arc length for their boxes.

> The seam pair matters: sorting by angle in a flat list and only checking
> list-adjacency misses the highest-angle ↔ lowest-angle pair, which are true
> circular neighbors. The per-ring circular pass closes that hole.

### 6. Radial monotonicity clamp
Independent per-ring growth can let an inner ring overtake an outer one
(ring 2 inside ring 1). Nodes on adjacent rings *can* share an angle, so the
required gap is the worst-case diagonal box separation:
`gap = √2 · max(max_width, max_height) + 30`. After growth:
`rings[g] = max(rings[g], rings[g−1] + gap)`.

### 7. K zoom
`K = rings[1] / 780`. Rings and node boxes are then **both** multiplied by K —
a uniform zoom of the already-validated base geometry. Scaling a clean layout
uniformly keeps it clean. (Scaling boxes *without* scaling rings — or
validating at one scale and rendering at another — silently invalidates every
separation. Validate in base units, zoom once, render.)

### 8. Chord bands
`R_out = max(rings) + 170K + 50` — outside every node envelope. Each chord
*source* node gets its own concentric band: `band_i = R_out + 140K · i`. The
chord is a constant-radius polyline sampled every ~3° along its angular span.
Since each band radius exceeds the extent of every node, and bands are
pairwise disjoint, chord polylines cannot pass over nodes, and bands cannot
intersect each other.

### 9. Label placement
One label per edge, wrapped on `·`/`;` at ~26 chars. Chord labels try several
points along their own band polyline (mid, quarter points) with small radial
offsets; spoke labels walk the straight span at t ∈ {0.42, 0.5, 0.34, …}
with an offset ring. Every candidate is checked against the canvas, all node
boxes, and all already-placed labels; the first collision-free candidate wins.
If nothing fits, the label falls back to the edge midpoint — the test suite
asserts every label is collision-free AND in-canvas, so a fallback firing on
your spec is a signal the spec is too dense: shorten labels or prune edges.

## Why each guarantee is true

1. **No node overlaps.** Same ring: tangential growth guarantees arc length
   ≥ box widths for every circular neighbor pair (the widest pair at the same
   angle on the same ring is exactly such a pair). Different rings: radial
   clamp guarantees center distance ≥ worst-case diagonal separation. Root:
   ring 1 radius ≫ root box.
2. **Tree edges stay in their wedge.** A node's angle is the midpoint of its
   leaf arc; its children's arcs partition (and sit inside) its arc. The
   straight segment from parent to child stays inside the cone spanned by the
   child's arc, and by induction inside the wedge at every depth — wedges are
   disjoint, so spokes never cross spokes or pass over nodes from other
   wedges.
3. **Chords stay outside.** Every chord point is at radius ≥ R_out >
   max(rings) + margin ≥ any node point's radius.
4. **Labels are collision-checked at placement time** against the final
   geometry (nodes, previously placed labels, canvas).
5. **Canvas** = max(node extents, outermost band + label margin) + padding.
6. **Reachability**: tree ∪ {synthetic orphan attachment} spans all nodes.
7. **Crossings**: per-source disjoint bands eliminate band-band crossings
   structurally; what remains is chords sharing a band (same source) whose
   angular intervals interleave — exactly what the annealer minimizes; the
   achieved count is reported deterministically.
8. **Determinism**: the only randomness is `random.Random(seed)`.

## Known approximation

The interleave objective treats a chord crossing the 0/2π seam as occupying
its complement interval, so seam-crossing pairs can be miscounted *during
optimization* (the reported final count uses the same convention, keeping the
metric consistent with the objective). This affects optimization quality only
— never structure. Chords' rendered polylines are unaffected.

## Failure modes the design eliminates

These were real bugs found by the invariant suite during development; they are
listed so future editors don't reintroduce them:

- Orphan nodes placed at radius 0 (center), stacking on the root.
- Mixed angle conventions ([0,2π) leaves vs (−π,π] internals) silently
  scrambling circular sorts and seam-pair checks.
- Vector-resultant parent angles pointing outside their own subtree arc.
- Flat-list adjacency checks missing the circular seam pair, so the tightest
  same-ring pair never constrained ring growth.
- Per-ring growth inverting ring order (ring 2 inside ring 1).
- Scaling boxes by K while positions stayed at un-scaled rings (double
  scaling) — or validating geometry at one scale and rendering at another.
- Chord labels placed without collision checks (only canvas bounds).
- `Counter` used without import on the auto-root path — crashes exactly when
  the user omits `root`, the most common quick-start path.
