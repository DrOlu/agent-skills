#!/usr/bin/env python3
"""RMAgent patient-zero — the backward graph walk, with honest termination.

THE PROBLEM THIS FIXES
---------------------
The old walk (hunt.py's lateral traversal) terminates when it runs out of
logon events — but it cannot tell you WHY it stopped. Two very different
outcomes look identical:

  (a) reached the origin: the oldest hop's initial access came from OUTSIDE
      the estate. The trace is complete. Patient zero is that host.
  (b) hit the retention boundary: the oldest hop's logons are simply gone
      (log rotated, or older than the window). The trace is INCOMPLETE.
      The oldest host you can see is NOT patient zero — it is just the
      oldest thing you can see.

Reporting (b) as (a) is a confident wrong answer, which is worse than no
answer. This module distinguishes them.

HOW
---
For each hop backward it records the EARLIEST logon it can see on that host
and the oldest event timestamp available in the Security log. If the earliest
logon in the window is newer than the oldest surviving event, the walk hit
RETENTION, not the origin. The result carries an explicit `termination`
field: "origin" | "retention-boundary" | "no-signal" | "blind-witness".

BLIND WITNESS: if attest reports blind_count > 0, the walk refuses to claim
an origin through that box — a blind witness produces confident false
negatives (the WS2 lesson).

Usage:
  python3 patient_zero.py --inventory estate.yaml --start ws2 --since 24h
  python3 patient_zero.py --inventory estate.yaml --start ws2 --since 24h --json

Read-only. No lake: each hop pulls at most `--limit` logons.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

MAX_HOPS = 8


def _to_hours(s: str) -> float:
    s = s.strip()
    if s.endswith("h"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) / 60
    if s.endswith("d"):
        return float(s[:-1]) * 24
    return float(s)


def _earliest_logon(edges_data: dict):
    """(timestamp_str, logon_dict) of the oldest tracked logon, or None."""
    logons = edges_data.get("logons") or []
    if not logons:
        return None
    with_ts = [l for l in logons if l.get("t")]
    if not with_ts:
        return None
    oldest = min(with_ts, key=lambda l: l["t"])
    return oldest.get("t"), oldest


def _oldest_event_available(row: dict) -> str | None:
    """Oldest Security-log event timestamp the witness still holds.

    Uses the existing `attest` answer's log-retention signal where present;
    otherwise returns None (unknown) — we never guess.
    """
    res = lib.ask(row, "attest", since_hours=1.0, limit=5)
    d = res.get("data") or {}
    return d.get("oldest_security_event") or None


def walk(inv: dict, start_id: str, since_h: float, limit: int) -> dict:
    """Backward walk from a symptom host. Returns hops + honest termination."""
    rows = lib.witnesses(inv)
    by_id = {r.get("id"): r for r in rows}
    addr_to_id = {r.get("address"): r.get("id") for r in rows if r.get("address")}

    start = by_id.get(start_id)
    if not start:
        return {"error": f"witness {start_id} not in inventory"}

    hops = []
    visited = set()
    current = start_id
    termination = None
    patient_zero = None

    for _ in range(MAX_HOPS):
        if current in visited:
            termination = "cycle"
            break
        visited.add(current)
        row = by_id.get(current)
        if not row:
            termination = "unknown-witness"
            break

        # --- blind check FIRST: never claim an origin through a blind witness
        att = lib.ask(row, "attest", since_hours=1.0, limit=5)
        ad = att.get("data") or {}
        blind = int(ad.get("blind_count") or 0)
        if blind > 0:
            hops.append({
                "host": current, "blind": True,
                "note": f"blind_count={blind} — cannot see logons; refusing to claim origin here",
            })
            termination = "blind-witness"
            break

        # --- edges for this host
        er = lib.ask(row, "edges", since_hours=since_h, limit=limit)
        ed = er.get("data") or {}
        early = _earliest_logon(ed)
        if not early:
            hops.append({"host": current, "note": "no tracked logons in window"})
            termination = "no-signal"
            break
        ts, oldest_logon = early
        src_ip = (oldest_logon.get("src") or "").strip()
        src_id = addr_to_id.get(src_ip)

        hops.append({
            "host": current,
            "earliest_logon_utc": ts,
            "src_ip": src_ip,
            "src_is_estate": bool(src_id),
            "src_witness": src_id,
            "logon": {k: oldest_logon.get(k) for k in ("t", "user", "type", "lid", "auth")},
        })

        if not src_id:
            # the oldest inbound logon came from OUTSIDE the estate
            patient_zero = current
            termination = "origin"
            break

        # continue backward into the estate
        current = src_id

    if termination is None:
        termination = "hop-limit"

    # --- retention honesty: is the earliest logon we relied on actually the
    # oldest thing in the log? If the log's OLDEST retained event is at or
    # after the earliest logon we walked to, then the log starts right where
    # our walk stopped — older logons may have existed and rotated away.
    # We stopped at a RETENTION BOUNDARY, not the origin.
    retention_limited = False
    if termination == "origin" and hops:
        last = hops[-1]
        row = by_id.get(last.get("host"))
        if row:
            oldest_evt = _oldest_event_available(row)
            relied = last.get("earliest_logon_utc")
            if oldest_evt and relied:
                # The earliest logon we relied on IS the oldest retained event
                # (or the log starts after it) → we are at the log's edge.
                # There is no visibility beyond it, so "external" may simply
                # mean "before the log began".
                if relied <= oldest_evt:
                    retention_limited = True
                    termination = "retention-boundary"
                    patient_zero = None

    return {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "start": start_id,
        "since_hours": since_h,
        "hops": hops,
        "hop_count": len(hops),
        "termination": termination,
        "retention_limited": retention_limited,
        "patient_zero": patient_zero,
        "confidence": ("high" if termination == "origin" and not retention_limited
                       else "low" if termination in ("retention-boundary", "blind-witness", "no-signal")
                       else "medium"),
        "note": {
            "origin": "the oldest hop's initial access came from outside the estate — trace complete",
            "retention-boundary": ("the walk stopped because logons older than the window are gone — "
                                   "the oldest host visible is NOT necessarily patient zero. widen --since "
                                   "or check the DC's logs."),
            "blind-witness": "a witness on the path cannot see logons (audit policy) — fix the policy, re-walk",
            "no-signal": "no tracked logons in the window on this host",
            "cycle": "the walk revisited a host (logon loop) — treat the cycle members as one unit",
            "hop-limit": f"stopped at {MAX_HOPS} hops — widen the window or walk manually from the last hop",
        }.get(termination, termination),
    }


def main():
    ap = argparse.ArgumentParser(description="RMAgent patient-zero backward walk")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--start", required=True, help="witness id where the symptom was found")
    ap.add_argument("--since", default="24h")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    inv = lib.load_inventory(args.inventory)
    result = walk(inv, args.start, _to_hours(args.since), args.limit)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result.get("error"):
        print("[patient-zero] " + result["error"])
        return
    print("[patient-zero] start=%s window=%s" % (result["start"], args.since))
    for i, h in enumerate(result["hops"]):
        if h.get("blind"):
            print("  hop %d  %s  BLIND (%s)" % (i, h["host"], h.get("note")))
            continue
        if not h.get("logon"):
            print("  hop %d  %s  (%s)" % (i, h["host"], h.get("note")))
            continue
        lg = h["logon"]
        print("  hop %d  %s  earliest=%s src=%s (%s) user=%s type=%s auth=%s"
              % (i, h["host"], (h.get("earliest_logon_utc") or "?")[:19],
                 h.get("src_ip") or "?",
                 "estate" if h.get("src_is_estate") else "EXTERNAL",
                 lg.get("user"), lg.get("type"), lg.get("auth")))
    print("  termination : %s" % result["termination"])
    print("  confidence  : %s" % result["confidence"])
    print("  patient zero: %s" % (result.get("patient_zero") or "(not established)"))
    print("  note        : %s" % result["note"])


if __name__ == "__main__":
    main()
