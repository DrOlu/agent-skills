#!/usr/bin/env python3
"""Hunter — walk tracked principals across Linux witnesses, serial, capped.

Does not copy the Windows hunt. Asks only the linux grain:
attest → sketch → edges → explain → attackmap on smoke.
Writes hops/holes into ~/.rmagent/cases (or --case-dir).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

WALK = ("attest", "sketch", "edges", "explain", "attackmap")
CASES = Path.home() / ".rmagent" / "cases"


def _write(case_dir: Path, name: str, obj) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    p = case_dir / name
    if name.endswith(".jsonl"):
        with p.open("a") as f:
            f.write(json.dumps(obj) + "\n")
        return
    data = []
    if p.exists():
        try:
            data = json.loads(p.read_text() or "[]")
        except Exception:
            data = []
    data.append(obj)
    p.write_text(json.dumps(data, indent=2, default=str))


def _smoke(skill: str, data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if skill == "attest":
        return int(data.get("failed_sudo_window") or 0) > 0 or int(data.get("blind_count") or 0) > 0
    if skill == "sketch":
        return bool(data.get("new_users_24h") or data.get("sudo_group_adds") or data.get("suid_recent"))
    if skill == "edges":
        return bool(data.get("accepted_ssh") or data.get("sudo_escalations") or data.get("root_outbound"))
    if skill == "explain":
        return bool(data.get("user_changes") or data.get("new_systemd_units") or data.get("new_cron"))
    if skill == "attackmap":
        return bool(data.get("findings") or data.get("ld_preload") or data.get("cron"))
    return False


def main():
    ap = argparse.ArgumentParser(description="RMAgent Linux hunt")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--since", default="2h")
    ap.add_argument("--case-dir")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    since_h = 2.0
    s = args.since.strip().lower()
    if s.endswith("h"):
        since_h = float(s[:-1] or 2)
    elif s.endswith("m"):
        since_h = float(s[:-1] or 30) / 60.0
    elif s.endswith("d"):
        since_h = float(s[:-1] or 1) * 24
    else:
        since_h = float(s)

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    case_dir = Path(args.case_dir) if args.case_dir else (CASES / time.strftime("linux-%Y%m%d-%H%M%S"))
    case_dir.mkdir(parents=True, exist_ok=True)
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[linux-hunt {t}] {len(rows)} witnesses → {case_dir}")

    for row in rows:
        wid = row.get("id")
        cd = lib.cooldown_left(wid)
        if cd > 0:
            hole = lib.hole(f"{wid} walk", f"cooldown {int(cd)}s")
            _write(case_dir, "holes.jsonl", {"t": t, **hole})
            print(f"  skip {wid} cooldown {int(cd)}s")
            continue
        smoke = False
        for q in WALK:
            if q not in (row.get("skills") or WALK):
                continue
            res = lib.ask(row, q, since_hours=since_h, limit=args.limit)
            if hasattr(lib, "record_ask"):
                lib.record_ask(case_dir, row, q, res)
            hop = {"witness": wid, "question": q, "ok": res.get("ok"),
                   "error": res.get("error"), "hole": res.get("hole")}
            data = res.get("data") or {}
            if res.get("ok") and isinstance(data, dict):
                hop["smoke"] = _smoke(q, data)
                smoke = smoke or hop["smoke"]
                if q == "attest":
                    hop["blind_count"] = data.get("blind_count")
                    hop["host"] = data.get("host")
            else:
                _write(case_dir, "holes.jsonl", {"t": t, "witness": wid, "question": q,
                                                 **(res.get("hole") or {"why": res.get("error")})})
            _write(case_dir, "path.json", hop)
            print(f"  {wid:8} {q:10} ok={res.get('ok')} smoke={hop.get('smoke')}")
            if q == "attest" and not res.get("ok"):
                break  # don't pile questions on a silent box
            if q == "attest" and int((data or {}).get("blind_count") or 0) > 0:
                print(f"  {wid:8} witness_blind — remaining answers are suspect")
        _ = smoke

    print(f"wrote {case_dir}")


if __name__ == "__main__":
    main()
