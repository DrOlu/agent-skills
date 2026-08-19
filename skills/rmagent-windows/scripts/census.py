#!/usr/bin/env python3
"""Census — the minute watch. Are the witnesses alive? Administrator/SYSTEM smoke.

All-windows estate: pywinrm with a max-3 knock budget (BoundedPool), not 20 in series.
Two missed attests on a host = Critical (written as a hole, not tight-retried).

Usage:
  python3 census.py --inventory estate.yaml
  python3 census.py --inventory estate.yaml --serial       # force serial (mixed estates)
"""
from __future__ import annotations
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import notify  # noqa: E402 — Telegram alerts on Critical

MAX_MISSES = 2  # Critical threshold


def knock(row, case_dir):
    res = lib.ask(row, "attest", since_hours=0.05, limit=10, timeout=lib.ASK_TIMEOUT_SEC)
    lib.record_ask(case_dir, row, "attest", res)
    return row.get("id"), res


def main():
    ap = argparse.ArgumentParser(description="RMAgent Census — minute watch")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--case-dir", help="case folder to record asks into")
    ap.add_argument("--serial", action="store_true", help="force serial knocks (mixed estates)")
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    case_dir = Path(args.case_dir) if args.case_dir else None
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[census {t}] {len(rows)} witnesses")

    serial = args.serial or any((r.get("door") or "winrm") != "winrm" for r in rows)
    results = []
    if serial:
        for r in rows:
            results.append(knock(r, case_dir))
    else:
        with ThreadPoolExecutor(max_workers=lib.MAX_CONCURRENT_ATTEND) as ex:
            futs = [ex.submit(knock, r, case_dir) for r in rows]
            for f in as_completed(futs):
                results.append(f.result())

    miss_count = {r.get("id"): 0 for r in rows}
    # BUG FIX (2026-08-19): the miss-state file used to live in CWD (or the case dir),
    # so consecutive runs from different directories / different case dirs never saw
    # each other's misses — "2 misses = Critical" could never trigger across runs.
    # It now lives in a stable per-user location.
    state = Path.home() / ".rmagent" / ".census_miss.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    try:
        prev = json.loads(state.read_text()) if state.exists() else {}
    except Exception:
        prev = {}
    for wid, _ in results:
        prev[wid] = prev.get(wid, 0)

    for wid, res in results:
        ok = res.get("ok")
        if ok and res.get("data"):
            d = res["data"]
            print(f"  ok   {wid:8} alive={d.get('alive')} "
                  f"admin_fail_60s={d.get('admin_failed_60s')} "
                  f"admin_ok_5m={d.get('admin_ok_5min')} "
                  f"local_admins={d.get('local_admin_count')} "
                  f"sys_conns={d.get('system_remote_conns')}")
            prev[wid] = 0
        else:
            prev[wid] = prev.get(wid, 0) + 1
            why = (res.get("hole") or {}).get("why") or res.get("error") or "no claim"
            level = "CRITICAL" if prev[wid] >= MAX_MISSES else "miss"
            print(f"  {level:8} {wid:8} hole — {why}  (misses={prev[wid]})")
            if case_dir and prev[wid] >= MAX_MISSES:
                h = lib.hole(f"{wid} attest", f"{MAX_MISSES} missed check-ins: {why}")
                with (case_dir / "holes.jsonl").open("a") as f:
                    f.write(json.dumps({"t": t, **h}) + "\n")
                notify.alert_critical(wid, why)

    try:
        state.write_text(json.dumps(prev))
    except OSError:
        pass


if __name__ == "__main__":
    main()
