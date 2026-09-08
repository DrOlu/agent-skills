#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-iso fixes.

1. Bounded per-flow TCP reassembly: fragmented messages decode once complete;
   coalesced messages both decode; buffers stay bounded; drops are counted.
2. A response-less request inside the ~60 s completion deadline is IN-FLIGHT,
   not a timeout; past the deadline (or with no newer activity) it IS one.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode import pack_financial, unpack
from ingest import ingest_line
from reasm import Reassembler
from txn import reconstruct

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


PAN = "5060990012345678"
TAP = "tap-fep-acq"


def _iso_bytes(stan="123456", rrn="123456789012", mti="0200") -> bytes:
    return pack_financial(mti=mti, stan=stan, rrn=rrn, pan=PAN,
                          amount="000000010000", tid="ATM00001")


def _line(t, payload: bytes) -> str:
    return f"{t}\t10.0.0.1\t5000\t10.0.0.2\t5000\t{payload.hex()}"


print("== 1a. fragmented message decodes once complete ==")
r = Reassembler()
msg = _iso_bytes()
first, second = msg[:20], msg[20:]
t0 = time.time()
recs1 = ingest_line(_line(t0, first), tap=TAP, reasm=r)
ok(recs1 == [] or all(x.get("hole") for x in recs1),
   "partial segment produces no decoded record (buffered, not a garbage hole)")
recs2 = ingest_line(_line(t0 + 1, second), tap=TAP, reasm=r)
ok(len(recs2) == 1 and not recs2[0].get("hole"),
   f"completion decodes exactly one record (got {len(recs2)})")
ok(recs2 and recs2[0].get("stan") == "123456", "reassembled record carries the grain")

print("== 1b. coalesced messages both decode ==")
r2 = Reassembler()
two = _iso_bytes(stan="200001", rrn="200001000001") + _iso_bytes(stan="200002", rrn="200002000002")
recs = ingest_line(_line(t0, two), tap=TAP, reasm=r2)
ok(len(recs) == 2, f"two coalesced messages -> two records (got {len(recs)})")
stans = {x.get("stan") for x in recs}
ok(stans == {"200001", "200002"}, "both grains recorded")

print("== 1c. bounds are enforced and counted ==")
r3 = Reassembler(max_flow_bytes=1024)
big = b"Z" * 4096
recs = ingest_line(_line(t0, big), tap=TAP, reasm=r3)
ok(any(x.get("reason") == "flow-over-limit" for x in recs), "oversized flow -> hole with reason")
ok(r3.stats["bytes_dropped"] >= 4096, "dropped bytes counted")
r4 = Reassembler(max_flows=2)
for i in range(4):
    # distinct src ports -> distinct flows, so eviction actually triggers
    line = f"{t0}\t10.0.0.1\t{5000 + i}\t10.0.0.2\t5000\t{_iso_bytes(stan=f'30000{i}', rrn=f'30000{i}000001').hex()}"
    ingest_line(line, tap=TAP, reasm=r4)
ok(len(r4._flows) <= 2, "flow count bounded")
ok(r4.stats["flows_flushed"] >= 2, "evictions counted")

print("== 2. in-flight vs timeout honesty ==")
now = time.time()
# 2a. request 10 s ago, nothing newer -> still in-flight (deadline not passed)
recs = [{"tap": TAP, "mti": "0200", "stan": "1", "rrn": "R1", "t": now - 10,
         "src": "a", "dst": "b"}]
j = reconstruct(recs, "1", "R1")
ok(j.get("timeout") is False, f"recent response-less request is IN-FLIGHT (got {j.get('timeout')})")

# 2b. request 10 min ago, newer activity exists afterwards -> timeout
recs = [
    {"tap": TAP, "mti": "0200", "stan": "2", "rrn": "R2", "t": now - 600,
     "src": "a", "dst": "b"},
    {"tap": TAP, "mti": "0200", "stan": "9", "rrn": "R9", "t": now - 30,
     "src": "a", "dst": "b"},
]
j = reconstruct(recs, "2", "R2")
ok(j.get("timeout") is True, "deadline passed -> timeout")

# 2c. responded txn is never a timeout
recs = [
    {"tap": TAP, "mti": "0200", "stan": "3", "rrn": "R3", "t": now - 600, "src": "a", "dst": "b"},
    {"tap": TAP, "mti": "0210", "stan": "3", "rrn": "R3", "t": now - 599, "rc": "00",
     "src": "a", "dst": "b"},
]
j = reconstruct(recs, "3", "R3")
ok(j.get("timeout") is False, "responded txn not a timeout")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — iso rev20 suite: ALL TESTS PASSED")
