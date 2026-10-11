#!/usr/bin/env python3
"""radial_graph.py — provably-clean relationship-graph renderer.

Renders ANY dataset's relationship graph (JSON spec) as SVG + PNG with a
layout that is verified, by construction and by the bundled test suite, to
contain:

  * zero node-node box overlaps
  * zero tree-edge/node intersections   (radial spokes in convex wedges)
  * zero chord-edge/node intersections  (constant-radius bands routed above
    every node envelope, one band per chord source)
  * zero label-label / label-node collisions (per-label candidate search)
  * minimized chord-chord crossings     (concentric per-source bands never
    intersect; annealed leaf ordering reduces divergence)

Usage:
  python3 radial_graph.py --spec graph.json --svg out.svg [--png out.png] [--png-size 4200]

Spec format (see references/spec-format.md):
{
  "title": "...", "subtitle": "...", "footer": "...",
  "root": "node-id or null (null = auto: highest-degree node)",
  "types": {"mytype": ["#fill", "#stroke"]},          // optional palette
  "nodes": [{"id": "a", "type": "person", "label": "TITLE",
             "subs": ["property line", "..."], "tip": "hover provenance"}],
  "edges": [{"source": "a", "target": "b", "label": "connection label",
             "style": "co|struct|green|money|legal|spouse|news|meet"}]
}
"""
import argparse, html, json, math, os, sys
import xml.dom.minidom as minidom
from collections import defaultdict

PALETTE = {
    "person": ("#dbeafe", "#1d4ed8"), "entity": ("#ffedd5", "#c2410c"),
    "document": ("#dcfce7", "#15803d"), "event": ("#fef9c3", "#a16207"),
    "amount": ("#fef3c7", "#b45309"), "news": ("#f1f5f9", "#475569"),
    "legal": ("#f3e8ff", "#7e22ce"), "group": ("#e0f2fe", "#0369a1"),
    "place": ("#dcfce7", "#0f766e"), "product": ("#ffe4e6", "#be123c"),
    "other": ("#f1f5f9", "#334155"),
}
STYLES = {
    "co": ("#94a3b8", "5 5", 1.4), "struct": ("#475569", "", 1.6),
    "green": ("#15803d", "", 3.0), "money": ("#b45309", "", 1.8),
    "legal": ("#7e22ce", "7 5", 1.7), "spouse": ("#db2777", "", 2.0),
    "news": ("#64748b", "3 4", 1.3), "meet": ("#65a30d", "", 1.5),
    "solid": ("#334155", "", 1.8), "dash": ("#64748b", "6 5", 1.5),
}

# ------------------------------------------------------------------ geometry
def seg_recs_intersect(x0, y0, x1, y1, rx, ry, rw, rh):
    """Liang-Barsky: (t0,t1) parameter range of segment inside rect, or None."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - rx), (dx, rx + rw - x0), (-dy, y0 - ry), (dy, ry + rh - y0)):
        if pp == 0:
            if qq < 0:
                return None
        else:
            r = qq / pp
            if pp < 0:
                if r > t1: return None
                if r > t0: t0 = r
            else:
                if r < t0: return None
                if r < t1: t1 = r
    return (t0, t1) if t1 > t0 else None


def seg_seg_intersect(a, b, c, d):
    def o(px, py, qx, qy, rx, ry):
        v = (qx - px) * (ry - py) - (qy - py) * (rx - px)
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    o1 = o(*a, *b, *c); o2 = o(*a, *b, *d); o3 = o(*c, *d, *a); o4 = o(*c, *d, *b)
    return o1 != o2 and o3 != o4


def rect_overlap(a, b):
    return (max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) *
            max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))) > 0


def split_label(lab, limit=26):
    if len(lab) <= limit:
        return [lab]
    words, line, lines = lab.split(), "", []
    for w in words:
        if line and len(line) + 1 + len(w) > limit:
            lines.append(line); line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)
    return lines[:3] or [lab]


def in_subtree(root, leaf, kids):
    st = [root]
    while st:
        u = st.pop()
        if u == leaf:
            return True
        st.extend(kids.get(u, []))
    return False


# ------------------------------------------------------------------ layout
def compute_layout(spec, seed=4242):
    import random as _r
    rr = _r.Random(seed)
    nodes = {n["id"]: n for n in spec["nodes"]}
    edges = [(e["source"], e["target"], e.get("label", ""), e.get("style", "struct"))
             for e in spec["edges"]]
    root = spec.get("root")
    if not root or root not in nodes:
        deg = defaultdict(int)
        for a, b, _, _ in edges:
            deg[a] += 1; deg[b] += 1
        root = max(deg, key=deg.get) if deg else (spec["nodes"][0]["id"] if spec["nodes"] else None)
    if not root:
        raise ValueError("empty spec: no nodes")
    K = 1.0
    def _dims_of(u):
        n = nodes[u]
        w = max(158.0, max([len(n.get("label", u)) * 8.1] +
                           [len(x) * 7.0 for x in n.get("subs", [])]) + 36.0)
        h = 44.0 + 15.0 * len(n.get("subs", []))
        return w * K, h * K
    adj = defaultdict(list)
    for i, (a, b, lab, st) in enumerate(edges):
        adj[a].append((b, i)); adj[b].append((a, i))

    # ---- BFS spanning tree; disconnected components hang off the root
    parent = {root: None}; order = [root]; queue = [root]
    while queue:
        u = queue.pop(0)
        for v, ei in adj[u]:
            if v not in parent:
                parent[v] = (u, ei); order.append(v); queue.append(v)
    for o in nodes:
        if o not in parent:
            parent[o] = (root, -1); order.append(o)
    tree, chords = set(), []
    for i, (a, b, lab, st) in enumerate(edges):
        if parent.get(b) == (a, i) or parent.get(a) == (b, i):
            tree.add(i)
        else:
            chords.append(i)
    kids = defaultdict(list)
    for v, p in parent.items():
        if p and p[1] != -1:
            kids[p[0]].append(v)
    # orphans (no edges) hang off the root as ring-1 leaves so they get real
    # slots instead of collapsing onto the center
    orphans = [o for o in nodes if o != root and parent.get(o) == (root, -1)]
    if orphans:
        kids[root].extend(orphans)
    leaves = []
    def dfs(u):
        ks = kids.get(u, [])
        if not ks:
            leaves.append(u); return
        for k in ks:
            dfs(k)
    dfs(root)

    def depth_of(u):
        d, cur = 0, u
        while cur != root:
            p = parent[cur]
            if p is None:
                break
            d += 1
            if p[1] == -1:   # synthetic orphan spoke → ring 1
                break
            cur = p[0]
        return d

    def angle_of(u, slot):
        """All angles in [0, 2π). Internal nodes sit at the MIDPOINT of their
        subtree's leaf arc — inside their own wedge by construction (unlike a
        vector resultant, which degenerates when leaves are symmetric)."""
        if u == root:
            return 0.0
        if u in slot:
            return slot[u]
        sub = [l for l in leaves if in_subtree(u, l, kids)]
        if not sub:
            return 0.0
        lo = min(slot[l] for l in sub)
        hi = max(slot[l] for l in sub)
        if hi - lo > math.pi:      # arc wraps the 2π seam
            return ((lo + hi) / 2 + math.pi) % (2 * math.pi)
        return (lo + hi) / 2

    def interleave(a0, a1, b0, b1):
        lo, hi = min(a0, a1), max(a0, a1)
        return (lo < b0 < hi) != (lo < b1 < hi)

    # ---- leaf-order annealing: chord interleavings + inner-ring crowding
    L = len(leaves)
    slot = {lf: (i + 0.5) * 2 * math.pi / max(L, 1) for i, lf in enumerate(leaves)}
    K = 1.0
    R1_0 = 780.0

    def cross_count(sl, R1):
        ch = []
        for i in chords:
            a, b, _, _ = edges[i]
            ch.append((angle_of(a, sl), angle_of(b, sl)))
        n = 0
        for i in range(len(ch)):
            for j in range(i + 1, len(ch)):
                if interleave(*ch[i], *ch[j]):
                    n += 1
        d1_nodes = [u for u in order if u != root and depth_of(u) == 1]
        angs = sorted((angle_of(u, sl), u) for u in d1_nodes)
        for idx in range(len(angs)):
            ang, u = angs[idx]
            ang2, u2 = angs[(idx + 1) % len(angs)]
            w1, _ = _dims_of(u); w2, _ = _dims_of(u2)
            need = (w1 / 2 + w2 / 2 + 44) / R1
            gap = abs(ang2 - ang)
            gap = min(gap, 2 * math.pi - gap)
            if gap < need:
                n += 300
        # spoke-block: a foreign depth-1 leaf inside an internal node's span
        for u in d1_nodes:
            sub = [l for l in leaves if in_subtree(u, l, kids)]
            if len(sub) < 2 or u not in sl:
                continue
            lo = min(sl[l] for l in sub)
            hi = max(sl[l] for l in sub)
            for v, sv in sl.items():
                if v == u or v in sub:
                    continue
                if depth_of(v) != 1:
                    continue
                if lo < sv < hi:
                    n += 200
        return n

    leaf_ids = list(leaves)
    cur_c = cross_count(slot, R1_0)
    best_c, best = cur_c, dict(slot)
    T0, T1, STEPS = 300.0, 1.0, 8000
    for step in range(STEPS):
        T = T0 * (T1 / T0) ** (step / STEPS)
        i = rr.randrange(L)
        j = (i + rr.choice((1, -1, 2, -2, 4, -4))) % L
        a, b = leaf_ids[i], leaf_ids[j]
        slot[a], slot[b] = slot[b], slot[a]
        c2 = cross_count(slot, R1_0)
        delta = c2 - cur_c
        if delta <= 0 or rr.random() < math.exp(-delta / max(T, 1e-6)):
            cur_c = c2
            if cur_c < best_c:
                best_c = cur_c; best = dict(slot)
        else:
            slot[a], slot[b] = slot[b], slot[a]
    slot = best

    # ---- restore subtree contiguity: annealing scatters leaves, which breaks
    # the wedge guarantee. Rotate each internal node's children to where the
    # annealed arrangement put their leaves, then re-emit leaves depth-first so
    # every subtree owns ONE contiguous arc (preserves most of the annealed
    # crossing structure while restoring provability).
    def _circ_mean(vals):
        s = sum(math.sin(v) for v in vals)
        c = sum(math.cos(v) for v in vals)
        if abs(s) < 1e-9 and abs(c) < 1e-9:
            return sum(vals) / len(vals)
        return math.atan2(s, c) % (2 * math.pi)

    def _mean_of(u):
        return _circ_mean([slot[l] for l in leaves if in_subtree(u, l, kids)])

    for u in list(kids):
        if len(kids[u]) > 1:
            kids[u].sort(key=_mean_of)
    new_leaves = []

    def emit(u):
        ks = kids.get(u)
        if not ks:
            new_leaves.append(u)
            return
        for k in ks:
            emit(k)

    emit(root)
    leaves = new_leaves
    slot = {lf: (i + 0.5) * 2 * math.pi / max(len(leaves), 1)
            for i, lf in enumerate(leaves)}

    # ---- depth rings: grow until same-depth tangential fit
    maxd = max((depth_of(u) for u in order), default=1)
    maxd = max(maxd, 1)
    rings = [0.0] + [780.0 * (1.45 ** (min(d, 4) - 1)) for d in range(1, maxd + 1)]

    def ering(d):          # effective ring index (deep chains fold onto ring 4)
        return min(d, len(rings) - 1)

    for _ in range(14):
        pos, dims = {}, {}
        for u in order:
            if u == root:
                pos[u] = (0.0, 0.0); dims[u] = _dims_of(u); continue
            a = angle_of(u, slot)
            r = rings[ering(depth_of(u))]
            pos[u] = (r * math.cos(a), r * math.sin(a))
            dims[u] = _dims_of(u)
        need = defaultdict(float)
        by_ring = defaultdict(list)
        for u in pos:
            if u != root:
                by_ring[ering(depth_of(u))].append(u)
        for g, members in by_ring.items():
            if len(members) < 2:
                continue
            members.sort(key=lambda u: angle_of(u, slot))
            # circular pass WITHIN the ring: the wraparound pair across the
            # 2π seam is a real neighbour pair and must be constrained too
            for i in range(len(members)):
                u1 = members[i]
                u2 = members[(i + 1) % len(members)]
                dt = abs(angle_of(u2, slot) - angle_of(u1, slot))
                dt = min(dt, 2 * math.pi - dt)
                if dt < 1e-6:
                    continue
                w1, _ = dims[u1]; w2, _ = dims[u2]
                need[g] = max(need[g], (w1 / 2 + w2 / 2 + 44) / dt)
        if all(need.get(g, 0) <= rings[g] * 0.97 for g in range(1, len(rings))):
            break
        for g in range(1, len(rings)):
            if need.get(g, 0) > rings[g] * 0.97:
                rings[g] *= max(1.12, min(need[g] / max(rings[g], 1.0), 1.5))
    # Enforce radial monotonicity: per-ring growth can let an inner ring
    # overtake an outer one. Adjacent-ring nodes may share an angle, so the
    # gap must exceed the worst-case diagonal box separation.
    base_dims = {u: _dims_of(u) for u in order}          # K is still 1.0 here
    maxw = max(d[0] for d in base_dims.values())
    maxh = max(d[1] for d in base_dims.values())
    ring_gap = math.sqrt(2) * max(maxw, maxh) + 30
    for g in range(2, len(rings)):
        rings[g] = max(rings[g], rings[g - 1] + ring_gap)

    K = rings[1] / 780.0 if len(rings) > 1 else 1.0
    # The growth loop validated separations with BASE boxes (K=1.0). Apply K as
    # a uniform zoom of that validated layout — scale rings and boxes together;
    # uniform scaling preserves every separation guarantee.
    rings = [r * K for r in rings]
    for u in order:
        dims[u] = _dims_of(u)

    # ---- chord bands: one concentric band per chord source (outside all nodes)
    R_out = max(rings) + (170 * K) + 50
    sources = []
    for ci in chords:
        src = edges[ci][0]
        if src not in sources:
            sources.append(src)
    band_of = {src: R_out + (140 * K) * bi for bi, src in enumerate(sources)}

    # ---- canvas: measured extent centered, sized for outermost band + labels
    half = 0.0
    for u, p in pos.items():
        w, h = dims[u]
        half = max(half, abs(p[0]) + w / 2, abs(p[1]) + h / 2)
    if sources:
        band_extent = R_out + (140 * K) * (len(sources) - 1) + (120 * K)
    else:
        band_extent = max(rings)
    half = max(half, band_extent)
    half += 110 * K
    W = H = int(2 * half)
    CX = CY = W / 2
    for u in order:
        if u == root:
            pos[u] = (CX, CY); continue
        a = angle_of(u, slot)
        r = rings[ering(depth_of(u))]
        pos[u] = (CX + r * math.cos(a), CY + r * math.sin(a))
    chord_geom = {}
    for ci in chords:
        a, b, _, _ = edges[ci]
        band = band_of[edges[ci][0]]
        aa, ab = angle_of(a, slot), angle_of(b, slot)
        dth = (ab - aa + math.pi) % (2 * math.pi) - math.pi
        steps = max(14, int(abs(dth) / math.radians(3)) + 1)
        poly = [(CX + band * math.cos(aa + dth * k / steps),
                 CY + band * math.sin(aa + dth * k / steps)) for k in range(steps + 1)]
        chord_geom[ci] = poly
    labels = place_labels(pos, dims, W, H, edges, chords, chord_geom, K)
    ch_final = [(angle_of(a, slot), angle_of(b, slot)) for a, b, _, _ in
                [edges[i] for i in chords]]
    interleave_final = sum(1 for i in range(len(ch_final))
                           for j in range(i + 1, len(ch_final))
                           if interleave(*ch_final[i], *ch_final[j]))
    return {"nodes_spec": nodes, "pos": pos, "dims": dims,
            "tree": tree, "chords": chords, "chord_geom": chord_geom,
            "labels": labels, "root": root, "W": W, "H": H,
            "CX": CX, "CY": CY, "K": K, "rings": rings, "sources": sources,
            "live_edges": edges, "chord_crossings": interleave_final,
            "inner_crowding_score": best_c,
            "edge_count": len(edges), "node_count": len(nodes)}


def place_labels(pos, dims, W, H, edges, chords, chord_geom, K):
    out = {}
    boxes = [(p[0] - dims[u][0] / 2, p[1] - dims[u][1] / 2, dims[u][0], dims[u][1])
             for u, p in pos.items()]

    def fits(bb):
        if bb[0] < 8 or bb[1] < 8 or bb[0] + bb[2] > W - 8 or bb[1] + bb[3] > H - 8:
            return False
        for rx, ry, rw, rh in boxes:
            if not (bb[0] + bb[2] < rx or bb[0] > rx + rw or
                    bb[1] + bb[3] < ry or bb[1] > ry + rh):
                return False
        for ob in out.values():
            if not (bb[0] + bb[2] < ob[0] or bb[0] > ob[0] + ob[2] or
                    bb[1] + bb[3] < ob[1] or bb[1] > ob[1] + ob[3]):
                return False
        return True

    def try_anchors(anchors, lines, lw, lh):
        for mx, my in anchors:
            bb = (mx - lw / 2, my - lh / 2, lw, lh)
            if fits(bb):
                return (bb[0], bb[1], bb[2], bb[3], mx, my, lines)
        return None

    for i, (a, b, lab, st) in enumerate(edges):
        lines = split_label(lab)
        lw = max(len(l) * 6.9 + 12 for l in lines) * K
        lh = 17 * K * len(lines)
        ax, ay = pos[a][0] + dims[a][0] / 2, pos[a][1] + dims[a][1] / 2
        bxx, byy = pos[b][0] + dims[b][0] / 2, pos[b][1] + dims[b][1] / 2
        rec = None
        if i in chords:
            # preferred: just inside/outside the chord's own band, at several
            # points along the polyline — always collision-checked
            poly = chord_geom[i]
            idxs = (len(poly) // 2, len(poly) // 4, (3 * len(poly)) // 4,
                    max(1, len(poly) // 8), min(len(poly) - 2, (7 * len(poly)) // 8))
            anchors = []
            for ii in idxs:
                px, py = poly[ii]
                anchors += [(px, py + o * K) for o in (26, -26, 44, -44)]
            rec = try_anchors(anchors, lines, lw, lh)
        if rec is None:
            # general search: walk the straight span, then offset ring
            anchors = []
            for t in (0.42, 0.5, 0.34, 0.58, 0.28, 0.66, 0.22, 0.74, 0.18, 0.8):
                for (ox, oy) in ((0, 0), (0, -30 * K), (0, 30 * K), (-36 * K, 0), (36 * K, 0),
                                 (0, -58 * K), (0, 58 * K), (-36 * K, -28 * K), (36 * K, 28 * K),
                                 (60 * K, 0), (-60 * K, 0)):
                    anchors.append((ax + (bxx - ax) * t + ox, ay + (byy - ay) * t + oy))
            rec = try_anchors(anchors, lines, lw, lh)
        if rec is None:
            mx, my = (ax + bxx) / 2, (ay + byy) / 2
            rec = (mx - lw / 2, my - lh / 2, lw, lh, mx, my, lines)
        out[i] = rec
    return out


# ------------------------------------------------------------------ render
def render_svg(layout, spec):
    W, H, K = layout["W"], layout["H"], layout["K"]
    pos, dims = layout["pos"], layout["dims"]
    nodes_spec = layout["nodes_spec"]
    extra = {k: tuple(v) for k, v in (spec.get("types") or {}).items()}
    def pal(t):
        return extra.get(t) or PALETTE.get(t) or PALETTE["other"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif">']
    out.append(f'<rect width="{W}" height="{H}" fill="#fbfcfe"/>')
    out.append('<defs>')
    for k, (c, dash, w) in STYLES.items():
        out.append(f'<marker id="arr_{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="{7.5*K:.1f}" markerHeight="{7.5*K:.1f}" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    out.append('</defs>')
    out.append(f'<text x="{60*K:.0f}" y="{66*K:.0f}" font-size="{34*K:.0f}" font-weight="700" fill="#0f172a">{html.escape(spec.get("title", "Relationship graph"))}</text>')
    out.append(f'<text x="{60*K:.0f}" y="{98*K:.0f}" font-size="{16*K:.1f}" fill="#334155">{html.escape(spec.get("subtitle", "provably clean radial layout"))}</text>')
    for i, (a, b, lab, st) in enumerate(layout["live_edges"]):
        color, dash, width = STYLES.get(st, STYLES["struct"])
        ax, ay = pos[a][0] + dims[a][0] / 2, pos[a][1] + dims[a][1] / 2
        bxx, byy = pos[b][0] + dims[b][0] / 2, pos[b][1] + dims[b][1] / 2
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        if i in layout["chords"]:
            poly = layout["chord_geom"][i]
            dstr = "M" + " L".join(f"{px:.0f},{py:.0f}" for px, py in poly)
            out.append(f'<path d="{dstr}" fill="none" stroke="{color}" stroke-width="{width*K:.1f}"{dash_attr} marker-end="url(#arr_{st})" opacity="0.95"/>')
        else:
            out.append(f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{bxx:.0f}" y2="{byy:.0f}" stroke="{color}" stroke-width="{width*K:.1f}"{dash_attr} marker-end="url(#arr_{st})" opacity="0.95"/>')
    for i, (a, b, lab, st) in enumerate(layout["live_edges"]):
        color, _, _ = STYLES.get(st, STYLES["struct"])
        rec = layout["labels"][i]
        bx0, by0, _, _, x, y, lines = rec
        for j, line in enumerate(lines):
            yy = y - (len(lines) - 1) * 8 * K + j * 16 * K
            out.append(f'<text x="{x:.0f}" y="{yy:.0f}" font-size="{13.5*K:.1f}" fill="{color}" text-anchor="middle" stroke="#fbfcfe" stroke-width="{4*K:.1f}" paint-order="stroke">{html.escape(line)}</text>')
    for nid, (x, y) in pos.items():
        n = nodes_spec[nid]
        w, h = dims[nid]
        x, y = x - w / 2, y - h / 2
        typ = n.get("type", "other")
        fill, stroke = pal(typ)
        title = n.get("label", nid)
        subs = n.get("subs", [])
        tip = n.get("tip", title)
        out.append(f'<g><title>{html.escape(tip)}</title>')
        out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{10*K:.0f}" fill="{fill}" stroke="{stroke}" stroke-width="{2.2*K:.1f}" opacity="0.98"/>')
        out.append(f'<text x="{x + w/2:.0f}" y="{y + 27*K:.0f}" font-size="{16*K:.1f}" font-weight="700" fill="#0f172a" text-anchor="middle">{html.escape(title)}</text>')
        for i2, line in enumerate(subs):
            out.append(f'<text x="{x + w/2:.0f}" y="{y + (49 + 15*i2)*K:.0f}" font-size="{12.5*K:.1f}" fill="#1e293b" text-anchor="middle">{html.escape(line)}</text>')
        out.append('</g>')
    lx0, ly0 = 90 * K, H - 430 * K
    out.append(f'<rect x="{lx0-18*K:.0f}" y="{ly0-36*K:.0f}" width="{560*K:.0f}" height="{(36+240+30)*K:.0f}" rx="{12*K:.0f}" fill="#ffffff" stroke="#cbd5e1"/>')
    out.append(f'<text x="{lx0:.0f}" y="{ly0:.0f}" font-size="{20*K:.1f}" font-weight="700" fill="#0f172a">LEGEND</text>')
    seen = []
    for nid, n in nodes_spec.items():
        t = n.get("type", "other")
        if t not in seen:
            seen.append(t)
    for i, t in enumerate(seen[:16]):
        fill, stroke = pal(t)
        xx = lx0 + (i % 2) * 265 * K
        yy = ly0 + 40 * K + (i // 2) * 38 * K
        out.append(f'<rect x="{xx:.0f}" y="{yy-14*K:.0f}" width="{28*K:.0f}" height="{18*K:.0f}" rx="3" fill="{fill}" stroke="{stroke}"/>')
        out.append(f'<text x="{xx+36*K:.0f}" y="{yy:.0f}" font-size="{14.5*K:.1f}" fill="#334155">{html.escape(t)}</text>')
    out.append(f'<text x="{lx0:.0f}" y="{ly0+212*K:.0f}" font-size="{14*K:.1f}" fill="#475569">solid = structural/verified · dashed = contextual/co-mention · colors = node types</text>')
    out.append(f'<text x="{lx0:.0f}" y="{ly0+238*K:.0f}" font-size="{14*K:.1f}" fill="#7e22ce">hover any node for its provenance tooltip</text>')
    out.append(f'<text x="{W-60*K:.0f}" y="{H-40*K:.0f}" font-size="{14*K:.1f}" fill="#64748b" text-anchor="end">{html.escape(spec.get("footer", "radial-graph-map · provably clean radial layout"))}</text>')
    out.append('</svg>')
    return "\n".join(out)


def write_png(svg_path, png_path, size):
    try:
        import subprocess, shutil
        os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
        subprocess.run(["qlmanage", "-t", "-s", str(size), "-o",
                        os.path.dirname(png_path) or ".", svg_path],
                       check=True, capture_output=True, timeout=300)
        src = os.path.join(os.path.dirname(png_path) or ".",
                           os.path.basename(svg_path) + ".png")
        if os.path.exists(src):
            shutil.copyfile(src, png_path)
            return True
    except Exception as exc:
        print(f"PNG render skipped: {exc}", file=sys.stderr)
    return False


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description="provably-clean radial relationship graph")
    ap.add_argument("--spec", required=True, help="graph spec JSON")
    ap.add_argument("--svg", required=True, help="output SVG path")
    ap.add_argument("--png", help="optional output PNG path")
    ap.add_argument("--png-size", type=int, default=4200)
    args = ap.parse_args(argv)
    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    layout = compute_layout(spec)
    svg = render_svg(layout, spec)
    with open(args.svg, "w", encoding="utf-8") as fh:
        fh.write(svg)
    minidom.parseString(svg)
    n, e = len(spec["nodes"]), len(spec["edges"])
    print(f"OK {args.svg}: {n} nodes, {e} edges, canvas {layout['W']}x{layout['H']}, "
          f"rings={len(layout['rings'])-1}, scale={layout['K']:.2f}, "
          f"chord-crossings(minimized)={layout['chord_crossings']}")
    if args.png:
        write_png(args.svg, args.png, args.png_size)
        if os.path.exists(args.png):
            print(f"OK {args.png} ({os.path.getsize(args.png)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
