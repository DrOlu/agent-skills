"""graph_bridge — reusable runtime graph layer for neuralOS instances.

Drop into any instance directory alongside graph_edges.json (emitted by
discover_relationships.py). Feed parsed records per table; the property
graph is built AT FETCH TIME from those records — never stored, never stale.

Serves the ≤3 graph probes (references/graph-standards.md):

  overview(records)          node/edge counts, provenance, disjoint warnings, Mermaid
  neighbors(records, frag)   one-hop adjacency (capped, provenance included)
  connect(records, a, b)     bridge-traversed path with value continuity,
                             or an honest {"reachable": false, ...}

Contract:
- the model picks; this module traverses (the 121M model cannot hop);
- every edge carries provenance; declared candidates that verify with zero
  overlap over full records are DOWNGRADED to disjoint — no fabricated joins;
- all returns are capped digests.
"""
import json


def _stringify(v):
    """Scalars and stringified lists both (the normalization contract)."""
    if isinstance(v, list):
        return [str(x) for x in v]
    s = str(v)
    if s.startswith("[") and s.endswith("]"):
        try:
            return [str(x) for x in json.loads(s)]
        except Exception:
            return [s]
    return [s]


class GraphLayer:
    def __init__(self, edges_file, mermaid_cap=30, result_cap=25):
        with open(edges_file) as fh:
            decl = json.load(fh)
        self.edges_decl = decl.get("edges", [])
        self.disjoint_decl = decl.get("disjoint", [])
        self.mermaid_cap = mermaid_cap
        self.result_cap = result_cap

    # -------------------------------------------------- indexing + verify
    def _keyvals(self, records_by_table):
        """{table: {col: set(str values)}} over FULL parsed records."""
        kv = {}
        for t, recs in (records_by_table or {}).items():
            cols = {}
            for rec in recs:
                for col, v in rec.items():
                    if v is None:
                        continue
                    cols.setdefault(col, set()).update(_stringify(v))
            kv[t] = cols
        return kv

    def _verify(self, records_by_table):
        """Re-check every declared edge against the FULL records."""
        kv = self._keyvals(records_by_table)
        verified, demoted, dangling = [], [], []
        for e in self.edges_decl:
            av = kv.get(e["a"], {}).get(e["a_col"], set())
            bv = kv.get(e["b"], {}).get(e["b_col"], set())
            if not av or not bv:
                demoted.append({**e, "why": "column absent/empty at runtime"})
                continue
            ov = av & bv
            if not ov:
                demoted.append({**e, "why": "zero value overlap over full records",
                                "runtime_tier": "disjoint"})
                continue
            tier = "exact_fk" if e["tier"] == "exact_fk" or len(ov) >= 5 else "candidate"
            verified.append({**e, "runtime_tier": tier,
                             "matched_pairs": len(ov),
                             "sample_keys": sorted(ov)[:5]})
            d = len(av - bv)
            if d:
                dangling.append({"a": e["a"], "b": e["b"], "column": e["a_col"],
                                 "dangling_refs": d,
                                 "note": "%d values in %s.%s have no match in %s.%s"
                                         % (d, e["a"], e["a_col"], e["b"], e["b_col"])})
        return {"kv": kv, "verified": verified, "demoted": demoted,
                "dangling": dangling}

    def _edge_between(self, g, t1, t2):
        for e in g["verified"]:
            if (e["a"], e["b"]) in ((t1, t2), (t2, t1)):
                return e
        return None

    # -------------------------------------------------- probes
    def overview(self, records_by_table):
        g = self._verify(records_by_table)
        nodes = [{"table": t, "rows": len(recs)}
                 for t, recs in (records_by_table or {}).items()]
        return {
            "nodes": nodes,
            "edges_total": len(g["verified"]),
            "edges_verified": [{"a": e["a"], "via": e["a_col"], "b": e["b"],
                                "tier": e["runtime_tier"],
                                "matched_pairs": e["matched_pairs"]}
                               for e in g["verified"]],
            "disjoint_edges": len(g["demoted"]),
            "disjoint": [{"a": e["a"], "b": e["b"], "column": e["a_col"],
                          "why": e.get("why")} for e in g["demoted"]],
            "profile_declared_disjoint": self.disjoint_decl,
            "dangling": g["dangling"][:10],
            "mermaid": self._mermaid(g),
        }

    def neighbors(self, records_by_table, node_fragment):
        g = self._verify(records_by_table)
        frag = str(node_fragment).lower()
        hits = []
        for t, cols in sorted(g["kv"].items()):
            for col in sorted(cols):
                for v in sorted(cols[col]):
                    if frag in v.lower():
                        hits.append((t, col, v))
        if not hits:
            return {"error": "no node matches %r" % node_fragment,
                    "hint": "search by id/name fragment; graph_overview lists node tables"}
        out = []
        for t, col, v in hits[:5]:
            links = []
            for e in g["verified"]:
                if e["a"] == t and e["a_col"] == col and \
                        v in g["kv"].get(e["b"], {}).get(e["b_col"], set()):
                    links.append({"to": "%s.%s=%s" % (e["b"], e["b_col"], v),
                                  "tier": e["runtime_tier"]})
                elif e["b"] == t and e["b_col"] == col and \
                        v in g["kv"].get(e["a"], {}).get(e["a_col"], set()):
                    links.append({"to": "%s.%s=%s" % (e["a"], e["a_col"], v),
                                  "tier": e["runtime_tier"]})
            if links:
                out.append({"node": "%s.%s=%s" % (t, col, v), "links": links})
        return {"fragment": node_fragment, "matches": out[:self.result_cap],
                "matches_total": len(out)}

    def connect(self, records_by_table, a_frag, b_frag):
        """Table-level BFS where every hop must share at least one real key
        value (value continuity), with fragments present at both ends."""
        g = self._verify(records_by_table)
        adj = {}
        for e in g["verified"]:
            adj.setdefault(e["a"], set()).add(e["b"])
            adj.setdefault(e["b"], set()).add(e["a"])

        def tables_with(frag):
            return [t for t, cols in g["kv"].items()
                    if any(frag.lower() in v.lower()
                           for vals in cols.values() for v in vals)]

        starts, targets = tables_with(a_frag), tables_with(b_frag)
        if not starts:
            return {"reachable": False, "from": a_frag, "to": b_frag,
                    "why": "no node matches source fragment %r" % a_frag}
        if not targets:
            return {"reachable": False, "from": a_frag, "to": b_frag,
                    "why": "no node matches target fragment %r" % b_frag}

        paths = []
        for t0 in sorted(starts):
            queue = [(t0, {t0}, [])]
            while queue and len(paths) < 3:
                t, seen_t, chain = queue.pop(0)
                if t in targets and chain:
                    paths.append({"route": [c["via"] for c in chain],
                                  "shared_values": self._continuity(g, chain)})
                    continue
                for nb in sorted(adj.get(t, set()) - seen_t):
                    e = self._edge_between(g, t, nb)
                    if e is None:
                        continue
                    queue.append((nb, seen_t | {nb}, chain + [{
                        "via": "%s.%s <-> %s.%s" % (e["a"], e["a_col"],
                                                    e["b"], e["b_col"]),
                        "a": e["a"], "col": e["a_col"], "b": e["b"]}]))
        if paths:
            return {"reachable": True, "from": a_frag, "to": b_frag,
                    "paths": paths[:3]}
        return {"reachable": False, "from": a_frag, "to": b_frag,
                "why": "no verified edge path between these nodes "
                       "(graph_overview lists the disjoint/dead columns)"}

    def _continuity(self, g, chain):
        """Intersection of shared key values along a chain (max 5 reported)."""
        if not chain:
            return []
        shared = None
        for c in chain:
            ov = g["kv"].get(c["a"], {}).get(c["col"], set()) & \
                 g["kv"].get(c["b"], {}).get(c["col"], set())
            shared = ov if shared is None else (shared & ov or shared)
        return sorted(shared or set())[:5]

    def _mermaid(self, g):
        lines, count = ["graph LR"], 0
        for e in g["verified"][:self.mermaid_cap]:
            lines.append('  %s -- "%s (%s)" --> %s' % (e["a"], e["a_col"],
                                                       e["runtime_tier"], e["b"]))
            count += 1
        extra = len(g["verified"]) - count
        if extra > 0:
            lines.append('  more["+%d more edges"]' % extra)
        return "\n".join(lines) if count else None