#!/usr/bin/env python3
"""Relationship discovery for the graph layer (see references/graph-standards.md).

Reads a profile.json (the skill's Phase-1 output) and emits graph_edges.json:
node declarations, edge candidates between table pairs with provenance
(rule + confidence tier), and — critically — DISJOINT findings: column pairs
that share a NAME but whose values never overlap, which must be reported,
never used as joins.

Confidence tiers:
  exact_fk   value overlap proven within the profile sample (still
             re-verified at runtime over full records by graph_bridge)
  candidate  shared column name only — a guess, always labelled low
  disjoint   shared name, zero value overlap — a data-quality fact

Usage:
  python3 discover_relationships.py --profile profile.json --out graph_edges.json
"""
import argparse
import json
import re


def snake(name):
    return re.sub(r"[^0-9a-zA-Z_]+", "_", name).strip("_").lower()


def column_names(table):
    cols = table.get("columns") or []
    return [c["name"] for c in cols]


def value_overlap(a_vals, b_vals):
    """Return count of a-values found in b-values (capped lists)."""
    bset = {v for v in b_vals if v not in ("None", "none", "")}
    return sum(1 for v in a_vals if v in bset)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-cap", type=int, default=200,
                    help="max sample values considered per column")
    args = ap.parse_args()

    profile = json.load(open(args.profile))
    tables = profile["source"]["tables"]
    nodes, edges, disjoint = [], [], []

    def col_map(t):
        return {c["name"]: c for c in (t.get("columns") or [])}

    for t in tables:
        nodes.append({"table": t["name"], "rows": t.get("db_row_count", 0),
                      "label_hint": t["name"].upper()})

    for i, a in enumerate(tables):
        ca = col_map(a)
        for b in tables[i + 1:]:
            cb = col_map(b)
            # only consider "key-like" shared names: ids, foreign keys, codes
            for col in ca:
                if col not in cb:
                    continue
                keyish = (col.endswith("_id") or col.endswith("_key") or
                          col in ("txn_id", "account_id", "name", "email",
                                  "hostname", "zone", "id") or
                          col.startswith("id"))
                if not keyish:
                    continue
                av = [str(v) for v in sample_vals(a, col)][:args.sample_cap]
                bv = [str(v) for v in sample_vals(b, col)][:args.sample_cap]
                if not av or not bv:
                    continue
                ov = value_overlap(av, bv)
                ov_rev = value_overlap(bv, av)
                if ov == 0 and ov_rev == 0:
                    disjoint.append({
                        "a": a["name"], "b": b["name"], "column": col,
                        "note": "shared column name, zero sample value overlap — "
                                "join NOT valid; surface as data-quality finding"})
                    continue
                best = max(ov, ov_rev)
                denom = max(len(av), len(bv), 1)
                # sample overlap is suggestive only; runtime confirms over full records
                tier = "exact_fk" if best / denom >= 0.5 else "candidate"
                edges.append({
                    "a": a["name"], "a_col": col, "b": b["name"], "b_col": col,
                    "rule": "value_overlap_in_sample",
                    "tier": tier,
                    "sample_matches": best,
                    "cardinality_hint": "N:M" if best > 1 else "1:N",
                    "sample_keys": sorted(set(
                        [v for v in av if v in set(bv)] +
                        [v for v in bv if v in set(av)]))[:5]})

    out = {"profiled_at": profile.get("profiled_at"),
           "nodes": nodes, "edges": edges, "disjoint": disjoint,
           "standards": "references/graph-standards.md"}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"nodes={len(nodes)} edges={len(edges)} "
          f"(exact_fk={sum(1 for e in edges if e.get('tier') == 'exact_fk')}, "
          f"candidate={sum(1 for e in edges if e.get('tier') == 'candidate')}) "
          f"disjoint={len(disjoint)}")


def sample_vals(table, col):
    """Prefer column sample_values; fall back to scanning sample_records."""
    for c in (table.get("columns") or []):
        if c["name"] == col and c.get("sample_values"):
            return [str(v) for v in c["sample_values"]]
    return [str(r.get(col)) for r in (table.get("sample_records") or [])
            if r.get(col) is not None]


if __name__ == "__main__":
    main()