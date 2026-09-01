#!/usr/bin/env python3
"""RMAgent canary watch — the standing tripwire.

THE PROBLEM THIS SOLVES
-----------------------
Phase 0 is PULL: a question only gets asked when a hunt runs. If your hunt
cadence is hourly, you are structurally late for everything except
persistence. That is the gap between "a hunt habit" and "runtime detection".

The canary closes most of that gap with almost no cost, because a canary hit
needs no correlation to be a finding: the decoy exists only to be touched, so
any authentication attempt against it is an answer. A watcher that asks ONE
small question on a short interval gives you a tripwire instead of a graph
walk — detection moves from "after a chain of logons" to "at the first probe".

DESIGN (still no lake, still no agent on the box)
-------------------------------------------------
  - One allowlisted question per witness per tick: `canary`.
  - A short interval (default 60s) — this is the detection window.
  - State is a single small JSON file: the last-seen hit timestamp per
    witness. Nothing else is stored. No events are copied home.
  - Alert ONCE per new hit window, then stay quiet until a NEWER hit appears
    (dedup by timestamp, not by cooldown — a cooldown can hide a second hit).
  - A witness that goes unreachable is reported as a HOLE, never as "clean".
  - Exits non-zero if any witness tripped, so a scheduler can chain response.

This is still watch-only. It never actuates. It tells a human (or a
supervisor) that the tripwire fired; the response is the operator's call.

Usage:
  python3 canary_watch.py --inventory ~/estate.yaml            # foreground
  python3 canary_watch.py --inventory ~/estate.yaml --once     # single pass (cron)
  python3 canary_watch.py --inventory ~/estate.yaml --interval 30
  python3 canary_watch.py --inventory ~/estate.yaml --once --json

Cron form (recommended — survives restarts, no daemon to babysit):
  * * * * * python3 ~/.agents/skills/rmagent-so/scripts/canary_watch.py \
      --inventory ~/estate.yaml --once --quiet >> ~/.rmagent/canary_watch.log 2>&1
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib      # noqa: E402
import notify    # noqa: E402

STATE_FILE = Path.home() / ".rmagent" / "canary_state.json"
# the detection window: how far back each tick looks. Slightly longer than
# the tick interval so a hit at a boundary is never missed.
WINDOW_SLACK = 1.25


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def _newest_hit_ts(data: dict) -> str | None:
    """Newest hit timestamp in a canary answer, or None."""
    hits = data.get("hits") or []
    ts = [h.get("t") for h in hits if h.get("t")]
    return max(ts) if ts else None


def check_witness(row: dict, since_hours: float, limit: int) -> dict:
    """Ask the canary question of one witness. Returns a small result dict."""
    res = lib.ask(row, "canary", since_hours=since_hours, limit=limit)
    if not res.get("ok"):
        return {"witness": row.get("id"), "ok": False,
                "hole": res.get("hole") or res.get("error") or "unreachable"}
    d = res.get("data") or {}
    return {
        "witness": row.get("id"),
        "ok": True,
        "tripped": bool(d.get("tripped")),
        "hit_count": int(d.get("hit_count") or 0),
        "armed": d.get("armed") or [],
        "armed_count": int(d.get("armed_count") or 0),
        "sources": d.get("sources") or [],
        "hits": d.get("hits") or [],
        "newest_hit": _newest_hit_ts(d),
    }


def run_pass(inv: dict, interval_s: int, limit: int, quiet: bool = False,
             state: dict | None = None) -> dict:
    """One sweep of every canary-capable witness. Returns the pass result."""
    rows = [r for r in lib.witnesses(inv)
            if "canary" in (r.get("skills") or [])]
    if not rows:
        return {"error": "no witness advertises the canary skill — add it to the inventory"}

    state = state if state is not None else _load_state()
    # the window: look back slightly further than the tick so nothing is missed
    since_h = (interval_s * WINDOW_SLACK) / 3600.0

    results, tripped, holes, unarmed = [], [], [], []
    for row in rows:
        wid = row.get("id")
        r = check_witness(row, since_h, limit)
        results.append(r)

        if not r.get("ok"):
            holes.append(wid)
            continue
        if r["armed_count"] == 0:
            unarmed.append(wid)
            continue
        if not r["tripped"]:
            continue

        # a hit. Is it NEW (newer than the last one we alerted on)?
        prev = state.get(wid) or ""
        newest = r.get("newest_hit") or ""
        # BUG FIX (audit): a hit with NO timestamp used to be silently DROPPED
        # (newest falsy -> the whole condition False -> "already alerted")
        # — a real attacker touching the decoy with timestamp-less events
        # would never alert. Now: no timestamp means we cannot dedup by time,
        # so we alert when the hit_count has GROWN since the last alert.
        if newest:
            is_new = newest > prev
        else:
            prev_n = state.get(f"{wid}#hits") or 0
            is_new = r["hit_count"] > prev_n
        if is_new:
            tripped.append(r)
            state[wid] = newest
            # for the no-timestamp path, remember the count we alerted on
            if not newest:
                state[f"{wid}#hits"] = r["hit_count"]
            if not quiet:
                srcs = ", ".join(r["sources"][:5]) or "no source recorded"
                print(f"  [TRIPPED] {wid}: {r['hit_count']} hit(s) from {srcs}")
                if newest:
                    print(f"            newest at {newest} — decoy exists only to be touched")
                else:
                    print(f"            (no hit timestamps — deduped by hit_count)")
        else:
            if not quiet:
                print(f"  [repeat ] {wid}: hit already alerted (newest {newest or 'n/a'})")

    out = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_seconds": interval_s,
        "witnesses": [r.get("id") for r in rows],
        "tripped": tripped,
        "holes": holes,
        "unarmed": unarmed,
        "results": results,
        "state": state,
    }

    # persist the dedup cursor BEFORE alerting, so a failed alert cannot spam
    if tripped:
        _save_state(state)

    # alert once per pass if anything tripped
    if tripped:
        lines = []
        for r in tripped:
            srcs = ", ".join(r["sources"][:5]) or "no source recorded"
            names = ", ".join(r["armed"][:3]) or "?"
            lines.append(f"  • {r['witness']}: {r['hit_count']} attempt(s) against decoy "
                         f"({names}) from {srcs}")
        body = "\n".join(lines)
        ok = notify.send(
            f"🔴 RMAgent CANARY TRIPPED\n"
            f"A decoy identity was touched. It exists only to be touched — treat as "
            f"patient-zero candidate.\n\n{body}\n\n"
            f"Respond with rmagent-actuate (block_ip / disable_user / rotate_credential). "
            f"Watch-only: this alert did not act.")
        if not quiet:
            print(f"  [alert  ] telegram={'sent' if ok else 'not configured (RMAgent_TELEGRAM_OFF or no creds)'}")

    if holes and not quiet:
        for h in holes:
            print(f"  [hole   ] {h}: unreachable — NOT clean, just not asked")
    if unarmed and not quiet:
        print(f"  [note   ] no canaries armed on: {', '.join(unarmed)} "
              f"(run actuate.py plant_canary)")

    _save_state(state)
    return out


def main():
    ap = argparse.ArgumentParser(description="RMAgent canary watch — the standing tripwire")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--interval", type=int, default=60,
                    help="seconds between ticks (default 60 = the detection window)")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--once", action="store_true",
                    help="single pass then exit (for cron); default is a foreground loop")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the pass result as JSON")
    args = ap.parse_args()

    inv = lib.load_inventory(args.inventory)

    if args.once:
        out = run_pass(inv, args.interval, args.limit, args.quiet)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        # exit non-zero if tripped, so a scheduler can chain response
        sys.exit(1 if out.get("tripped") else 0)

    # foreground loop
    print(f"[canary-watch] interval={args.interval}s  state={STATE_FILE}")
    print(f"[canary-watch] Ctrl-C to stop. For restart-proof operation use cron --once.")
    while True:
        if not args.quiet:
            print(f"[canary-watch] {time.strftime('%H:%M:%S')} sweep")
        out = run_pass(inv, args.interval, args.limit, args.quiet)
        if out.get("error"):
            print("[canary-watch] " + out["error"])
            sys.exit(2)
        if args.json:
            print(json.dumps({k: v for k, v in out.items() if k != "state"},
                             indent=2, default=str))
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
