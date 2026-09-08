#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-pay honesty fixes.

1. A failed/blind core hop yields "not-observed-at-core", never
   "never-reached-core" (which implied a verdict we could not prove).
2. Cap re-measures the FULL serialized answer after trimming.
3. Corroborated latencies carry evidence_class.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


SWITCH_OK = {"ok": True, "data": {"rows": [
    {"rrn": "100000000001", "stan": "000001", "in_ts": "2026-09-08T10:00:00Z",
     "out_ts": "2026-09-08T10:00:01Z", "rc": "00"},
]}}

print("== 1. core hop failure is NOT 'never-reached-core' ==")
CORE_DEAD = {"ok": False, "hole": {"why": "ssh: connection refused"}}
d = lib.hop_delta(SWITCH_OK, CORE_DEAD)
hops = d["data"]["hops"]
ok(d["data"]["termination"] == "core-hole", "termination reports core-hole")
ok(hops[0]["delay_on"] == "not-observed-at-core",
   f"delay_on is not-observed-at-core (got {hops[0]['delay_on']})")
ok(hops[0]["core_hop_ok"] is False, "core_hop_ok recorded")
ok(hops[0]["evidence_class"] == "candidate-association", "absence claims carry evidence_class")

print("== 2. sighted core with no row CAN say never-reached-core ==")
CORE_SIGHTED_EMPTY = {"ok": True, "data": {"rows": []}}
d = lib.hop_delta(SWITCH_OK, CORE_SIGHTED_EMPTY)
ok(d["data"]["hops"][0]["delay_on"] == "never-reached-core",
   "sighted core, no row -> never-reached-core is honest")
ok(d["data"]["hops"][0]["core_hop_ok"] is True, "core_hop_ok true")

print("== 3. corroborated latency carries evidence_class ==")
CORE_HIT = {"ok": True, "data": {"rows": [
    {"rrn": "100000000001", "stan": "000001",
     "recv_ts": "2026-09-08T10:00:00.25Z", "post_ts": "2026-09-08T10:00:08Z",
     "rc": "00"},
]}}
d = lib.hop_delta(SWITCH_OK, CORE_HIT)
h = d["data"]["hops"][0]
ok(h["delay_on"] == "finacle-posting", "slow core detected")
ok(h["evidence_class"] == "corroborated", "latency verdict marked corroborated")

print("== 4. cap re-measures the full answer ==")
big = {"ok": True, "data": {"rows": [{"rrn": "1", "note": "x" * 40000}]}}
out = lib._cap(big)
ok(out.get("ok") is False and out.get("hole"), "single oversized row -> hole, not passed through")
many = {"ok": True, "data": {"rows": [{"rrn": str(i), "note": "x" * 100} for i in range(500)]}}
out = lib._cap(many)
ok(out.get("capped") is True, "many small rows trimmed and capped")
ok(len((out.get("data") or {}).get("rows") or []) <= 3, "trimmed to 3 rows")
total = len(__import__("json").dumps(out, default=str).encode())
ok(total <= lib.MAX_PULL_BYTES, f"final serialized answer within cap ({total} bytes)")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — pay rev20 suite: ALL TESTS PASSED")
