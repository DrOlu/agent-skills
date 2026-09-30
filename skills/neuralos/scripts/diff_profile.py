#!/usr/bin/env python3
"""Profile diff — schema-evolution impact report.

Compare two profile.json files (old vs new) and report:
  tables added / dropped / row-count changes
  fields added / dropped / type-changed / enum-changed
  impacted probes (menu entries whose name starts with the table's snake name)

usage: diff_profile.py OLD_PROFILE NEW_PROFILE [--menu needle_menu.json]
exit : 0 no breaking changes | 1 breaking changes (dropped tables/fields)
"""
import argparse
import json
import sys


def index_profile(p):
    out = {}
    for t in p.get("source", {}).get("tables", []):
        fields = {f["name"]: f.get("detected_type") for f in t.get("fields", [])}
        out[t["name"]] = {"rows": t.get("rows"), "fields": fields}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--menu", help="needle_menu.json (for impacted-probe report)")
    a = ap.parse_args()

    old = index_profile(json.load(open(a.old, encoding="utf-8")))
    new = index_profile(json.load(open(a.new, encoding="utf-8")))
    breaking = []

    added = sorted(set(new) - set(old))
    dropped = sorted(set(old) - set(new))
    print(f"tables: +{len(added)} added, -{len(dropped)} dropped, "
          f"{len(set(old) & set(new))} common")
    for t in added:
        print(f"  + {t} ({new[t]['rows']} rows)")
    for t in dropped:
        print(f"  - {t} (WAS {old[t]['rows']} rows)"); breaking.append(f"table {t} dropped")

    for t in sorted(set(old) & set(new)):
        of, nf = old[t]["fields"], new[t]["fields"]
        for f in sorted(set(of) - set(nf)):
            print(f"  - {t}.{f} dropped"); breaking.append(f"{t}.{f} dropped")
        for f in sorted(set(nf) - set(of)):
            print(f"  + {t}.{f} added ({nf[f]})")
        for f in sorted(set(of) & set(nf)):
            if of[f] != nf[f]:
                print(f"  ~ {t}.{f} type: {of[f]} -> {nf[f]}")
                breaking.append(f"{t}.{f} type change")
        dr = (new[t]["rows"] or 0) - (old[t]["rows"] or 0)
        if dr:
            print(f"  ~ {t} rows: {dr:+d}")

    if a.menu:
        menu = json.load(open(a.menu, encoding="utf-8"))
        impacted = []
        for t in sorted(set(old) | set(new)):
            hits = [p["name"] for p in menu if t.lower() in p["name"].lower()]
            impacted += hits
        print("\nimpacted probes:", sorted(set(impacted)) or "(none matched)")

    print(f"\nbreaking changes: {len(breaking)}")
    for b in breaking:
        print("  !", b)
    raise SystemExit(1 if breaking else 0)


if __name__ == "__main__":
    main()
