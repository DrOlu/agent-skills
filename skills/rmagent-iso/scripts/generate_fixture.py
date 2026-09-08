#!/usr/bin/env python3
"""Build demo rings: 40 healthy on-us withdrawals + 3 incidents.

Incidents (stable STANs for the worked examples):
  STAN 123456 / RRN 123456789012  — slow Finacle (Segment D ~2.4s)
  STAN 654321 / RRN 654321000001  — timeout (0200 seen, no 0210)
  STAN 111222 / RRN 111222000051  — decline RC=51, hops complete

No Segment A tap is populated — DWD candidates are honest holes.
PAN is packed then masked; the ring must never contain the raw value.
"""
from __future__ import annotations

import time
from pathlib import Path

from decode import pack_financial, unpack_record
from ring import Ring

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = SKILL_DIR / "examples" / "rings"

PAN = "5060990012345678"  # lab only; must not appear in the ring
ACQ = "tap-fep-acq"
CBA = "tap-fep-cba"
SRC_ACQ, DST_FEP = "10.10.1.10:5000", "10.10.2.20:5000"
SRC_FEP, DST_CBA = "10.10.2.20:6000", "10.10.3.30:6000"


def _put(acq: Ring, cba: Ring, ej: Ring | None = None, *, t0: float, stan: str, rrn: str, tid: str,
         amount: str, b_req=0.020, d=0.100, b_resp=0.020, rc="00",
         drop_resp=False, dispense: bool = False) -> None:
    req = pack_financial(mti="0200", stan=stan, rrn=rrn, pan=PAN, amount=amount, tid=tid)
    resp = pack_financial(mti="0210", stan=stan, rrn=rrn, pan=PAN, amount=amount, tid=tid, rc=rc)
    acq.append(unpack_record(req, tap=ACQ, t=t0, src=SRC_ACQ, dst=DST_FEP))
    cba.append(unpack_record(req, tap=CBA, t=t0 + b_req, src=SRC_FEP, dst=DST_CBA))
    if drop_resp:
        return
    t_resp = t0 + b_req + d + b_resp
    cba.append(unpack_record(resp, tap=CBA, t=t0 + b_req + d, src=DST_CBA, dst=SRC_FEP))
    acq.append(unpack_record(resp, tap=ACQ, t=t_resp, src=DST_FEP, dst=SRC_ACQ))
    if dispense and ej is not None:
        ej.append(unpack_record(resp, tap="tap-term-ej", t=t_resp + 0.040, src="atm", dst="ej"))


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in (f"{ACQ}.jsonl", f"{CBA}.jsonl", "tap-term-ej.jsonl"):
        p = out / name
        p.write_text("")
    acq = Ring(out / f"{ACQ}.jsonl")
    cba = Ring(out / f"{CBA}.jsonl")
    ej = Ring(out / "tap-term-ej.jsonl")
    ej.init()

    t_base = time.time() - 1800  # 30 min ago so --since 1h sees them

    # 40 healthy — baseline n ≥ 30, EJ completion present
    for i in range(40):
        stan = f"{100000 + i}"
        rrn = f"{100000000000 + i}"
        _put(acq, cba, ej, t0=t_base + i * 2.0, stan=stan, rrn=rrn,
             tid=f"ATM{i:04d}"[:8], amount="000000010000",
             b_req=0.018 + (i % 5) * 0.002, d=0.080 + (i % 7) * 0.010,
             b_resp=0.015 + (i % 3) * 0.003, dispense=True)

    # slow Finacle + approved, NO EJ completion → DWD candidate
    _put(acq, cba, ej, t0=t_base + 900, stan="123456", rrn="123456789012",
         tid="ATM00001", amount="000000020000",
         b_req=0.025, d=2.375, b_resp=0.030, rc="00", dispense=False)

    # timeout — last_seen = cba_0200. REV 20: placed EARLY in the stream so
    # >60 s of later ring activity exists after it — a txn with no 0210 is
    # only a TIMEOUT once the ~60 s completion deadline has visibly passed;
    # a request near the head of the ring is honestly in-flight.
    _put(acq, cba, ej, t0=t_base + 100, stan="654321", rrn="654321000001",
         tid="ATM00002", amount="000000005000",
         b_req=0.022, drop_resp=True)

    # decline
    _put(acq, cba, ej, t0=t_base + 940, stan="111222", rrn="111222000051",
         tid="POS00003", amount="000000015000",
         b_req=0.020, d=0.090, b_resp=0.018, rc="51")

    print(f"wrote rings under {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    generate(Path(args.out))
