#!/usr/bin/env python3
"""pay hunt — attest both hops, pull txn rows, hop_delta. Ticket is the grain.

  python3 hunt.py --inventory examples/estate.yaml --ticket RRN-000000123456
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib


def main():
    ap = argparse.ArgumentParser(description="rmagent-pay hunt")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--ticket", required=True, help="STAN or RRN (e.g. RRN-000000123456)")
    ap.add_argument("--since", type=float, default=24.0, help="hours (default 24 — fixtures are dated)")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    switch_row = next((r for r in rows if (r.get("role") or "").lower() in ("fep", "switch", "postilion")), None)
    core_row = next((r for r in rows if (r.get("role") or "").lower() in ("cba", "core", "finacle")), None)
    if not switch_row or not core_row:
        sys.exit("inventory needs one role:fep (Postilion) and one role:cba (Finacle)")

    print(f"ticket {args.ticket}")
    print(f"  switch {switch_row['id']}  core {core_row['id']}")

    sa = lib.ask(switch_row, "pay_attest", since_hours=args.since, ticket=args.ticket)
    ca = lib.ask(core_row, "pay_attest", since_hours=args.since, ticket=args.ticket)
    print(f"  pay_attest switch blind={ (sa.get('data') or {}).get('blind') } ok={sa.get('ok')}")
    print(f"  pay_attest core   blind={ (ca.get('data') or {}).get('blind') } ok={ca.get('ok')}")

    if (sa.get("data") or {}).get("blind"):
        print("  HOLE switch is blind (no STAN/RRN in artifact) — do not conclude Postilion was fine")
    if (ca.get("data") or {}).get("blind"):
        print("  HOLE core is blind — do not conclude Finacle was fine")

    sw = lib.ask(switch_row, "switch_txn", since_hours=args.since, limit=args.limit, ticket=args.ticket)
    co = lib.ask(core_row, "core_auth", since_hours=args.since, limit=args.limit, ticket=args.ticket)
    print(f"  switch_txn rows={len((sw.get('data') or {}).get('rows') or [])} ok={sw.get('ok')}")
    print(f"  core_auth  rows={len((co.get('data') or {}).get('rows') or [])} ok={co.get('ok')}")

    delta = lib.hop_delta(sw, co)
    d = delta.get("data") or {}
    print(f"  hop_delta termination={d.get('termination')}")
    for h in d.get("hops") or []:
        print(f"    rrn={h.get('rrn')} delay_on={h.get('delay_on')} "
              f"ingress_ms={h.get('ingress_ms')} core_ms={h.get('core_ms')} "
              f"switch_rc={h.get('switch_rc')} core_rc={h.get('core_rc')}")
    print(json.dumps(delta.get("data"), indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
