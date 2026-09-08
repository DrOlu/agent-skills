#!/usr/bin/env python3
"""Pure-logic tests for rmagent-iso. No SPAN, no Postilion."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from decode import pack_financial, unpack, unpack_record
from generate_fixture import PAN, generate
from iso import assert_no_pan, grain, mask_pan
from lib import ask
from txn import reconstruct

N = 0
F = 0


def check(cond: bool, msg: str) -> None:
    global N, F
    N += 1
    if cond:
        print(f"  ok  {msg}")
    else:
        F += 1
        print(f"  FAIL {msg}")


def test_mask() -> None:
    print("mask")
    check(mask_pan(PAN) == "506099******5678", "first6 last4")
    check("*" in mask_pan(PAN), "stars present")
    try:
        assert_no_pan({"pan": PAN})
        check(False, "forbidden pan key")
    except ValueError:
        check(True, "forbidden pan key")


def test_roundtrip() -> None:
    print("decode roundtrip")
    buf = pack_financial(mti="0200", stan="123456", rrn="123456789012",
                         pan=PAN, amount="000000020000", tid="ATM00001")
    fields = unpack(buf)
    check(fields["mti"] == "0200", "mti")
    check(fields[11] == "123456", "stan")
    check(fields[37].strip() == "123456789012", "rrn")
    rec = unpack_record(buf, tap="tap-fep-acq", t=1.0)
    check(rec["pan_masked"] == "506099******5678", "masked on unpack_record")
    check(PAN not in json.dumps(rec), "raw PAN absent from record json")


def test_journeys() -> None:
    print("journeys")
    d = Path(tempfile.mkdtemp(prefix="rmagent-iso-"))
    generate(d)
    raw = (d / "tap-fep-acq.jsonl").read_text() + (d / "tap-fep-cba.jsonl").read_text()
    check(PAN not in raw, "raw PAN never in rings")

    att = ask("txnattest", rings=d)
    check(att["blind_check"] == "ok", "attest sighted")
    check("txnfail" not in json.dumps(ask("actuate", rings=d)), "actuate not a question")
    check(ask("actuate", rings=d).get("reason") == "not-allowlisted", "actuate rejected")

    slow = ask("txntrace", rings=d, stan="123456", rrn="123456789012")
    check(slow.get("hole") is False, "slow txn present")
    check(slow["hops"]["D"]["ms"] and slow["hops"]["D"]["ms"] > 2000, "D is the wait (~2.4s)")
    check(slow["slowest_hop"]["hop"] == "D", "slowest hop D")
    check(slow["hops"]["A"]["hole"] is True, "A is a hole")
    check(abs((slow["hops"]["B_req"]["ms"] or 0) - 25) < 2, "B_req ~25ms")

    hops = ask("txnhops", rings=d, stan="123456", rrn="123456789012")
    check(hops["slowest_hop"]["hop"] == "D", "hops agrees")

    to = reconstruct(
        ask.__defaults__ and [],  # noqa: dummy to keep import used
        "654321", "654321000001",
    ) if False else ask("txntrace", rings=d, stan="654321", rrn="654321000001")
    check(to.get("timeout") is True, "timeout flagged")
    check(to.get("last_seen") == "cba_0200", "last seen cba 0200")
    check(to.get("total_seen_ms") is None, "no total without 0210")

    fail = ask("txnfail", rings=d)
    stans_to = {r["stan"] for r in fail["timeouts"]}
    check("654321" in stans_to, "timeout in txnfail")
    dwd_stans = {r["stan"] for r in fail["debit_without_dispense_candidates"]}
    check("123456" in dwd_stans, "approved+no EJ = DWD candidate")
    check("CANDIDATE" in (fail["debit_without_dispense_candidates"][0].get("note") or fail["honest"]),
          "DWD is candidate not proof")

    decl = {r["stan"] for r in fail["declines"]}
    check("111222" in decl, "RC=51 in declines")

    slowq = ask("txnslow", rings=d, threshold_ms=800)
    check(slowq["n_slow"] >= 1, "at least one slow")
    check(slowq["rows"][0]["stan"] == "123456", "slowest is 123456")

    base = ask("txnbaseline", rings=d)
    check(base.get("hole") is False, "baseline n>=30")
    check(base["n"] >= 30, "n floor")
    check(base["hops"]["D"]["p50"] < 500, "healthy D p50 well under 500ms")

    missing = ask("txntrace", rings=d, stan="000000", rrn="999999999999")
    check(missing.get("hole") is True and missing.get("reason") == "not-in-ring", "unknown STAN is a hole")

    check(grain("123456", "123456789012") == "stan=123456;rrn=123456789012", "grain format")


def main() -> int:
    test_mask()
    test_roundtrip()
    test_journeys()
    print(f"\n{N - F}/{N} passed, {F} failed")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
