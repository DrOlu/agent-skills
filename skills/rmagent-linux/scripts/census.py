#!/usr/bin/env python3
"""Census — minute watch for Linux/macOS witnesses (SSH door).

Two missed attests = Critical. History under ~/.rmagent (not the skill tree).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

MAX_MISSES = 2
HISTORY = Path.home() / ".rmagent" / "census_history.jsonl"
HISTORY_MAX = 200
MISS_STATE = Path.home() / ".rmagent" / ".census_miss.json"


def _record_history(t: str, wid: str, d: dict | None) -> None:
    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        entry = {"t": t, "witness": wid, "plane": "linux"}
        if d:
            for k in ("failed_sudo_window", "root_logins_recent", "uptime_s",
                      "blind_count", "blind_check"):
                if k in d:
                    entry[k] = d.get(k)
        else:
            entry["silent"] = True
        with HISTORY.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        lines = HISTORY.read_text().splitlines()
        if len(lines) > HISTORY_MAX:
            HISTORY.write_text("\n".join(lines[-HISTORY_MAX:]) + "\n")
    except OSError:
        pass


def knock(row):
    res = lib.ask(row, "attest", since_hours=0.05, limit=10, timeout=25)
    wid = row.get("id")
    if res.get("ok"):
        lib.clear_silent(wid)
    else:
        lib.mark_silent(wid, (res.get("hole") or {}).get("why") or res.get("error") or "census miss")
    return wid, res


def main():
    ap = argparse.ArgumentParser(description="RMAgent Linux census")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--case-dir")
    args = ap.parse_args()
    inv = lib.load_inventory(args.inventory)
    rows = [r for r in lib.witnesses(inv)
            if (r.get("door") or "").lower() == "ssh"
            or (r.get("os") or "").lower() in ("linux", "darwin", "aix", "unix")]
    if not rows:
        rows = lib.witnesses(inv)
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[linux-census {t}] {len(rows)} witnesses")
    MISS_STATE.parent.mkdir(parents=True, exist_ok=True)
    try:
        prev = json.loads(MISS_STATE.read_text()) if MISS_STATE.exists() else {}
    except Exception:
        prev = {}
    case_dir = Path(args.case_dir) if args.case_dir else None
    for r in rows:
        wid, res = knock(r)
        lib.record_ask(case_dir, r, "attest", res) if hasattr(lib, "record_ask") else None
        if res.get("ok") and res.get("data"):
            d = res["data"]
            blind = d.get("blind_count", "?")
            print(f"  ok   {wid:8} host={d.get('host')} up={d.get('uptime_s')} "
                  f"sudo_fail={d.get('failed_sudo_window')} blind={blind}")
            prev[wid] = 0
            _record_history(t, wid, d)
        else:
            prev[wid] = prev.get(wid, 0) + 1
            why = (res.get("hole") or {}).get("why") or res.get("error") or "no claim"
            level = "CRITICAL" if prev[wid] >= MAX_MISSES else "miss"
            print(f"  {level:8} {wid:8} hole — {why}  (misses={prev[wid]})")
            _record_history(t, wid, None)
    try:
        MISS_STATE.write_text(json.dumps(prev))
        MISS_STATE.chmod(0o600)
    except OSError:
        pass


if __name__ == "__main__":
    main()
