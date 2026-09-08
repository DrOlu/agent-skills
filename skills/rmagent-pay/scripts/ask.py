#!/usr/bin/env python3
"""One question: python3 ask.py --inventory ../examples/estate.yaml --witness postilion-1 --skill switch_txn --ticket RRN-000000123456"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

ap = argparse.ArgumentParser()
ap.add_argument("--inventory", required=True)
ap.add_argument("--witness", required=True)
ap.add_argument("--skill", required=True)
ap.add_argument("--ticket", default="")
ap.add_argument("--since", type=float, default=24.0)
ap.add_argument("--limit", type=int, default=20)
args = ap.parse_args()
inv = lib.load_inventory(args.inventory)
row = lib.find(inv, args.witness)
if not row:
    sys.exit(f"no witness {args.witness}")
r = lib.ask(row, args.skill, since_hours=args.since, limit=args.limit, ticket=args.ticket)
print(json.dumps(r, indent=2, default=str)[:8000])
sys.exit(0 if r.get("ok") else 1)
