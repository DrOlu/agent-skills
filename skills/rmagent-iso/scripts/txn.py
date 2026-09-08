#!/usr/bin/env python3
"""Reconstruct one ISO journey and measure hops.

Two-tap model (estate-iso.yaml):
  tap-fep-acq  Segment B  acquirer ↔ Postilion
  tap-fep-cba  Segment C  Postilion ↔ Finacle

Hop math for on-us 0200/0210:
  B_req     = t_cba_req  - t_acq_req     Postilion inbound switch
  D         = t_cba_resp - t_cba_req     Finacle inferred (not a Finacle probe)
  B_resp    = t_acq_resp - t_cba_resp    Postilion outbound switch
  total     = t_acq_resp - t_acq_req     FEP-visible RTT
  A, E-to-terminal: holes unless EJ tap is present
"""
from __future__ import annotations

from typing import Any

from iso import CLOCK_SKEW_WARN_MS, grain, key_of

ACQ = "tap-fep-acq"
CBA = "tap-fep-cba"
EJ = "tap-term-ej"


def _ms(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round((a - b) * 1000.0, 3)


def _first(recs: list[dict], *, tap: str, mti: str) -> dict | None:
    for r in recs:
        if r.get("tap") == tap and r.get("mti") == mti:
            return r
    return None


def _pick(recs: list[dict], stan: str | None, rrn: str | None) -> list[dict]:
    want = grain(stan, rrn)
    out = [r for r in recs if key_of(r) == want]
    out.sort(key=lambda r: (r.get("t") or 0, r.get("tap") or "", r.get("mti") or ""))
    return out


def reconstruct(recs: list[dict], stan: str, rrn: str) -> dict[str, Any]:
    picked = _pick(recs, stan, rrn)
    if not picked:
        return {
            "grain": grain(stan, rrn),
            "hole": True,
            "reason": "not-in-ring",
            "note": "STAN/RRN not in any tap ring for this window. Retention-boundary or never seen.",
        }

    acq_req = _first(picked, tap=ACQ, mti="0200")
    cba_req = _first(picked, tap=CBA, mti="0200")
    cba_resp = _first(picked, tap=CBA, mti="0210")
    acq_resp = _first(picked, tap=ACQ, mti="0210")
    ej_disp = next((r for r in picked if r.get("tap") == EJ and r.get("mti") in ("0210", "dispense")), None)

    hops = {
        "A": {
            "segment": "A",
            "name": "terminal ↔ acquirer",
            "ms": None,
            "hole": True,
            "reason": "no-terminal-tap" if not ej_disp else "not-timed",
        },
        "B_req": {
            "segment": "B",
            "name": "Postilion inbound (acq 0200 → cba 0200)",
            "ms": _ms(cba_req.get("t") if cba_req else None, acq_req.get("t") if acq_req else None),
        },
        "D": {
            "segment": "D",
            "name": "Finacle inferred (cba 0200 → cba 0210)",
            "ms": _ms(cba_resp.get("t") if cba_resp else None, cba_req.get("t") if cba_req else None),
            "inferred": True,
        },
        "B_resp": {
            "segment": "B",
            "name": "Postilion outbound (cba 0210 → acq 0210)",
            "ms": _ms(acq_resp.get("t") if acq_resp else None, cba_resp.get("t") if cba_resp else None),
        },
        "E": {
            "segment": "E",
            "name": "return past acquirer (terminal still a hole)",
            "ms": None,
            "hole": True,
            "reason": "no-terminal-tap",
        },
    }
    for h in hops.values():
        if h.get("ms") is None and not h.get("hole"):
            h["hole"] = True
            h["reason"] = h.get("reason") or "missing-message"

    total = _ms(acq_resp.get("t") if acq_resp else None, acq_req.get("t") if acq_req else None)

    last_seen = None
    if acq_resp:
        last_seen = "acq_0210"
    elif cba_resp:
        last_seen = "cba_0210"
    elif cba_req:
        last_seen = "cba_0200"
    elif acq_req:
        last_seen = "acq_0200"

    # REV 20 (P0): a request without a response is NOT automatically a
    # timeout. It is a timeout only once the completion deadline has passed;
    # before that it is honestly "in-flight". The ring cannot know wall-clock
    # "now" at analysis time, so the deadline is expressed relative to the
    # newest event seen across the rings: if the newest ring event is older
    # than INFLIGHT_GRACE_S past the request, the txn can no longer complete
    # within the deadline and IS a timeout.
    INFLIGHT_GRACE_S = 60.0  # ISO financial txn completion deadline (industry ~30-60s)
    newest_anywhere = None
    for r in recs:
        rt = r.get("t")
        if rt is not None and (newest_anywhere is None or rt > newest_anywhere):
            newest_anywhere = rt
    timeout = False
    if acq_req is not None and acq_resp is None:
        if newest_anywhere is None:
            timeout = True  # nothing newer anywhere — the txn cannot have completed silently
        else:
            timeout = (newest_anywhere - acq_req.get("t", 0)) > INFLIGHT_GRACE_S
    rc = (acq_resp or cba_resp or {}).get("rc")
    approved = rc == "00"
    ej_present = any(r.get("tap") == EJ for r in recs)
    # DWD needs a sighted Segment A. An empty EJ ring is a hole, not 40 false DWD hits.
    dwd_candidate = bool(approved and ej_present and ej_disp is None)
    dwd_note = None
    if approved and not ej_present:
        dwd_note = (
            "Segment A is a hole (no EJ records). Cannot assert debit-without-dispense; "
            "confirm against ATM journal if the customer reports no cash."
        )
    elif dwd_candidate:
        dwd_note = (
            "0210 RC=00 at FEP, EJ tap is sighted, no matching completion. "
            "CANDIDATE — confirm against ATM journal before chargeback."
        )

    proto = acq_req or cba_req or picked[0]
    return {
        "grain": grain(stan, rrn),
        "hole": False,
        "stan": proto.get("stan"),
        "rrn": proto.get("rrn"),
        "tid": proto.get("tid"),
        "amount": proto.get("amount"),
        "pan_masked": proto.get("pan_masked"),
        "rc": rc,
        "n_messages": len(picked),
        "messages": [
            {"t": r.get("t"), "tap": r.get("tap"), "mti": r.get("mti"), "rc": r.get("rc")}
            for r in picked
        ],
        "hops": hops,
        "total_seen_ms": total,
        "last_seen": last_seen,
        "timeout": timeout,
        "debit_without_dispense_candidate": dwd_candidate,
        "dwd_note": dwd_note,
        "slowest_hop": _slowest(hops),
    }


def _slowest(hops: dict[str, dict]) -> dict[str, Any] | None:
    best = None
    for name, h in hops.items():
        ms = h.get("ms")
        if ms is None:
            continue
        if best is None or ms > best["ms"]:
            best = {"hop": name, "segment": h.get("segment"), "ms": ms, "name": h.get("name")}
    return best


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if p <= 0:
        return ys[0]
    if p >= 100:
        return ys[-1]
    k = (len(ys) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ys) - 1)
    if f == c:
        return ys[f]
    return ys[f] + (ys[c] - ys[f]) * (k - f)


def journeys(recs: list[dict]) -> list[dict[str, Any]]:
    keys = []
    seen = set()
    for r in recs:
        k = key_of(r)
        if k and k not in seen:
            seen.add(k)
            keys.append((r.get("stan"), r.get("rrn")))
    out = []
    for stan, rrn in keys:
        if not stan and not rrn:
            continue
        try:
            out.append(reconstruct(recs, stan or "", rrn or ""))
        except ValueError:
            continue
    return out
