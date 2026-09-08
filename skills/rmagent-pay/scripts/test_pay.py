#!/usr/bin/env python3
"""rmagent-pay tests — fixture door, no network."""
from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

PASS = FAIL = 0
FAILURES = []


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL  {label}")


INV = lib.load_inventory(str(lib.SKILL_DIR / "examples" / "estate.yaml"))
sw = lib.find(INV, "postilion-1")
co = lib.find(INV, "finacle-1")
bl = lib.find(INV, "blind-hop")
TICKET = "RRN-000000123456"

print("== allowlist")
ok("switch_txn" in lib.ALLOWED, "switch_txn allowlisted")
ok(lib.ask(sw, "edges").get("ok") is False, "edges refused (not pay)")

print("== pay_attest")
a = lib.ask(sw, "pay_attest", since_hours=24)
ok(a.get("ok") and a["data"].get("has_rrn"), "switch sees RRN")
ok(a["data"].get("blind") is False, "switch not blind")
b = lib.ask(bl, "pay_attest", since_hours=24)
ok(b.get("ok") and b["data"].get("blind") is True, "blind hop flagged")

print("== PCI")
r = lib.ask(sw, "switch_txn", since_hours=24, ticket=TICKET, limit=5)
rows = (r.get("data") or {}).get("rows") or []
ok(r.get("ok") and rows, "switch_txn hit for ticket")
ok(all("pin" not in json.dumps(x).lower() for x in rows), "no PIN in rows")
ok(all("*" in str(x.get("pan") or "*") for x in rows), "PAN masked")
ok("5399830000001111" not in json.dumps(r), "full PAN not in answer")

print("== hop_delta")
s = lib.ask(sw, "switch_txn", since_hours=24, ticket=TICKET)
c = lib.ask(co, "core_auth", since_hours=24, ticket=TICKET)
d = lib.hop_delta(s, c)
hops = (d.get("data") or {}).get("hops") or []
ok(d.get("ok") and hops, "hop_delta produced hops")
ok(hops[0].get("delay_on") in ("finacle-posting", "postilion-ingress"),
   f"delay_on set ({hops[0].get('delay_on')})")
ok(hops[0].get("core_ms") is not None and hops[0].get("core_ms") > hops[0].get("ingress_ms", 0),
   "core_ms > ingress_ms on the slow sample (Finacle posting)")

print("== honest hole")
sb = lib.ask(bl, "switch_txn", since_hours=24, ticket=TICKET)
why = (sb.get("hole") or {}).get("why", "") if isinstance(sb.get("hole"), dict) else str(sb.get("hole") or "")
ok(sb.get("ok") is False and "blind" in why.lower(),
   "blind switch_txn is a hole")
d2 = lib.hop_delta(sb, c)
ok((d2.get("data") or {}).get("termination") == "blind-witness",
   "hop_delta termination=blind-witness")

print("== never-reached-core")
only_switch = {"ok": True, "data": {"rows": [{"rrn": "000000999000", "stan": "000125",
    "in_ts": "2026-09-08T13:04:00.000Z", "out_ts": "2026-09-08T13:04:12.000Z", "rc": "91"}]}}
empty_core = {"ok": True, "data": {"rows": []}}
d3 = lib.hop_delta(only_switch, empty_core)
ok((d3.get("data") or {}).get("hops")[0].get("delay_on") == "never-reached-core",
   "RRN only on switch -> never-reached-core")

print("== mask_pan")
ok(lib.mask_pan("5399830000001111") == "539983******1111", "mask first6 last4")
ok("pinblock" not in json.dumps(lib.pci_scrub({"pinblock": "x", "rrn": "1"})), "pci_scrub drops pinblock")

print()
if FAIL:
    print(f"{FAIL} FAILED, {PASS} passed")
    for f in FAILURES:
        print(f"  x {f}")
    sys.exit(1)
print(f"{PASS} passed, 0 failed")
