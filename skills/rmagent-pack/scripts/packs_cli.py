#!/usr/bin/env python3
"""packs CLI — list packs/rules, or run a pack over a JSON rows file.

  python3 packs_cli.py list
  python3 packs_cli.py show kerberos_ad
  python3 packs_cli.py run kerberos_ad --rows rows.json
  python3 packs_cli.py run kerberos_ad --rows rows.json --blind dc.krb
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "packs"))
import packs as _packs  # noqa: E402

ap = argparse.ArgumentParser(description="rmagent-pack rule packs")
sub = ap.add_subparsers(dest="cmd", required=True)
sub.add_parser("list")
s = sub.add_parser("show"); s.add_argument("pack")
r = sub.add_parser("run"); r.add_argument("pack"); r.add_argument("--rows", required=True)
r.add_argument("--blind", nargs="*", default=[])
a = ap.parse_args()

if a.cmd == "list":
    for name, p in sorted(_packs.ALL_PACKS.items()):
        print(f"{name:18} {len(p.rules):2} rules  {p.title}")
elif a.cmd == "show":
    p = _packs.get(a.pack)
    print(f"{p.id}: {p.title}\n{p.description}\n")
    for rule in p.rules:
        t = rule.thresholds
        print(f"  {rule.id:18} [{rule.severity:8}] events={rule.events} "
              f"filters={list(rule.filters)} thresholds={t} {rule.technique}")
        print(f"      {rule.why}")
elif a.cmd == "run":
    rows = json.loads(Path(a.rows).read_text())
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("events") or []
    p = _packs.get(a.pack)
    out = p.run(rows, blind_sources=set(a.blind))
    print(json.dumps(out, indent=2, default=str))
    print(f"\n{p.n_fired if hasattr(p,'n_fired') else out['n_fired']}/{out['n_rules']} rules fired")
