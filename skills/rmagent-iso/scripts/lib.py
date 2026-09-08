#!/usr/bin/env python3
"""Allowlisted ask() for the ISO observatory.

Questions read rings. They never run tshark. Ingest is a separate door.
Oversized answers become holes. PAN never leaves unpack_record().
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from iso import BASELINE_MIN_N, MAX_PULL_BYTES, SLOW_THRESHOLD_MS, cap
from ring import Ring, load_all
from txn import journeys, percentile, reconstruct

ALLOWED = {"txnattest", "txntrace", "txnhops", "txnslow", "txnfail", "txnbaseline"}
# actuate is never a question — ask() returns not-allowlisted.
SKILL_DIR = Path(__file__).resolve().parents[1]


def _since_ts(since_hours: float | None) -> float | None:
    if since_hours is None:
        return None
    return time.time() - since_hours * 3600.0


def ask(question: str, *, rings: Path | str, stan: str | None = None,
        rrn: str | None = None, since_hours: float | None = None,
        threshold_ms: float = SLOW_THRESHOLD_MS,
        limit: int = 20) -> dict[str, Any]:
    if question not in ALLOWED:
        return {"hole": True, "reason": "not-allowlisted", "question": question}
    ring_dir = Path(rings)
    since = _since_ts(since_hours)
    recs = load_all(ring_dir, since=since)
    if question == "txnattest":
        ans = _txnattest(ring_dir)
    elif question == "txntrace":
        if not stan and not rrn:
            return {"hole": True, "reason": "need-stan-or-rrn"}
        ans = reconstruct(recs, stan or "", rrn or "")
        # trace is one journey; drop the full message list if still large
        ans = dict(ans)
        ans.pop("messages", None)
        ans["question"] = "txntrace"
    elif question == "txnhops":
        if not stan and not rrn:
            return {"hole": True, "reason": "need-stan-or-rrn"}
        j = reconstruct(recs, stan or "", rrn or "")
        ans = {
            "question": "txnhops",
            "grain": j.get("grain"),
            "hole": j.get("hole"),
            "reason": j.get("reason"),
            "hops": j.get("hops"),
            "total_seen_ms": j.get("total_seen_ms"),
            "slowest_hop": j.get("slowest_hop"),
            "last_seen": j.get("last_seen"),
            "timeout": j.get("timeout"),
        }
    elif question == "txnslow":
        ans = _txnslow(recs, threshold_ms=threshold_ms, limit=limit)
    elif question == "txnfail":
        ans = _txnfail(recs, limit=limit)
    elif question == "txnbaseline":
        ans = _txnbaseline(recs)
    else:
        return {"hole": True, "reason": "not-allowlisted"}
    out, capped = cap(ans)
    if capped:
        return out
    return out


def _txnattest(ring_dir: Path) -> dict[str, Any]:
    taps = []
    for name in ("tap-fep-acq.jsonl", "tap-fep-cba.jsonl", "tap-term-ej.jsonl"):
        st = Ring(ring_dir / name).stats()
        st["tap"] = name.replace(".jsonl", "")
        taps.append(st)
    required = [t for t in taps if t["tap"] in ("tap-fep-acq", "tap-fep-cba")]
    blind = [t["tap"] for t in required if t.get("blind")]
    return {
        "question": "txnattest",
        "taps": taps,
        "blind_check": "BLIND" if blind else "ok",
        "blind": blind,
        "note": "never trust no-findings while blind_check=BLIND",
    }


def _txnslow(recs: list[dict], *, threshold_ms: float, limit: int) -> dict[str, Any]:
    js = [j for j in journeys(recs) if not j.get("hole")]
    rows = []
    for j in js:
        total = j.get("total_seen_ms")
        slowest = j.get("slowest_hop") or {}
        if total is None:
            continue
        if total >= threshold_ms:
            rows.append({
                "stan": j.get("stan"),
                "rrn": j.get("rrn"),
                "tid": j.get("tid"),
                "total_seen_ms": total,
                "slowest_hop": slowest.get("hop"),
                "slowest_ms": slowest.get("ms"),
                "rc": j.get("rc"),
            })
    rows.sort(key=lambda r: -(r.get("total_seen_ms") or 0))
    return {
        "question": "txnslow",
        "threshold_ms": threshold_ms,
        "n_journeys": len(js),
        "n_slow": len(rows),
        "rows": rows[:limit],
    }


def _txnfail(recs: list[dict], *, limit: int) -> dict[str, Any]:
    js = [j for j in journeys(recs) if not j.get("hole")]
    timeouts = []
    dwd = []
    declines = []
    for j in js:
        row = {
            "stan": j.get("stan"),
            "rrn": j.get("rrn"),
            "tid": j.get("tid"),
            "last_seen": j.get("last_seen"),
            "rc": j.get("rc"),
            "total_seen_ms": j.get("total_seen_ms"),
        }
        if j.get("timeout"):
            timeouts.append(row)
        if j.get("debit_without_dispense_candidate"):
            dwd.append({**row, "note": j.get("dwd_note")})
        if j.get("rc") and j.get("rc") != "00" and not j.get("timeout"):
            declines.append(row)
    return {
        "question": "txnfail",
        "n_journeys": len(js),
        "timeouts": timeouts[:limit],
        "debit_without_dispense_candidates": dwd[:limit],
        "declines": declines[:limit],
        "honest": (
            "DWD candidates without Segment A are not proof of no-cash. "
            "Confirm against ATM EJ. Timeouts localize to last_seen tap."
        ),
    }


def _txnbaseline(recs: list[dict]) -> dict[str, Any]:
    js = [j for j in journeys(recs) if not j.get("hole") and j.get("total_seen_ms") is not None]
    n = len(js)
    if n < BASELINE_MIN_N:
        return {
            "question": "txnbaseline",
            "hole": True,
            "reason": "baseline-n-too-small",
            "n": n,
            "need": BASELINE_MIN_N,
            "note": "same floor as rmagent thinker. do not call 20 samples 'normal'.",
        }
    hops = {"B_req": [], "D": [], "B_resp": [], "total": []}
    for j in js:
        if j.get("total_seen_ms") is not None:
            hops["total"].append(j["total_seen_ms"])
        hh = j.get("hops") or {}
        for k in ("B_req", "D", "B_resp"):
            ms = (hh.get(k) or {}).get("ms")
            if ms is not None:
                hops[k].append(ms)

    def stats(xs: list[float]) -> dict[str, Any]:
        return {
            "n": len(xs),
            "p50": round(percentile(xs, 50) or 0, 3),
            "p95": round(percentile(xs, 95) or 0, 3),
            "p99": round(percentile(xs, 99) or 0, 3),
        }

    return {
        "question": "txnbaseline",
        "hole": False,
        "n": n,
        "hops": {k: stats(v) for k, v in hops.items()},
    }


def dump(ans: dict[str, Any]) -> str:
    return json.dumps(ans, indent=2, default=str)
