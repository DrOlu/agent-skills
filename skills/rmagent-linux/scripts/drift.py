#!/usr/bin/env python3
"""Baseline + drift for Linux witnesses. Baselines live in ~/.rmagent/baselines.

First run records sudoers / new units / ld.so.preload mtime.
Later runs diff. Growing blind_count is critical.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

BASE = Path.home() / ".rmagent" / "baselines"


def _snap(row: dict) -> dict:
    att = lib.ask(row, "attest", since_hours=24, limit=20)
    sk = lib.ask(row, "sketch", since_hours=24, limit=20)
    am = lib.ask(row, "attackmap", since_hours=24, limit=20)
    return {
        "attest_ok": bool(att.get("ok")),
        "blind_count": (att.get("data") or {}).get("blind_count"),
        "sudoers": (att.get("data") or {}).get("sudoers"),
        "new_users_24h": (sk.get("data") or {}).get("new_users_24h"),
        "suid_recent": (sk.get("data") or {}).get("suid_recent"),
        "attackmap": (am.get("data") or {}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    inv = lib.load_inventory(args.inventory)
    findings = []
    for row in lib.witnesses(inv):
        wid = row.get("id") or "unknown"
        path = BASE / f"linux-{wid}.json"
        now = _snap(row)
        if args.reset or not path.exists():
            path.write_text(json.dumps(now, indent=2, default=str))
            path.chmod(0o600)
            print(f"  baseline recorded {wid}")
            continue
        prev = json.loads(path.read_text())
        if (now.get("blind_count") or 0) > (prev.get("blind_count") or 0):
            findings.append({"kind": "witness_blind", "severity": "critical", "witness": wid,
                             "was": prev.get("blind_count"), "now": now.get("blind_count")})
        if (now.get("sudoers") or "") != (prev.get("sudoers") or ""):
            findings.append({"kind": "sudoers_changed", "severity": "high", "witness": wid})
        if now.get("suid_recent") and now.get("suid_recent") != prev.get("suid_recent"):
            findings.append({"kind": "suid_recent", "severity": "high", "witness": wid,
                             "now": now.get("suid_recent")})
        path.write_text(json.dumps(now, indent=2, default=str))
    if not findings:
        print("no drift")
        return
    for f in findings:
        print(f"  {f['severity']:8} {f['kind']:20} {f.get('witness')}")


if __name__ == "__main__":
    main()
