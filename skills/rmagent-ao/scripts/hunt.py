#!/usr/bin/env python3
"""Thin Agent Observatory hunt.

agents (census) → if smoke, agentstate/agenttrace/agentnet on that (host, agent).
No estate-wide transcript pull. Cases under ~/.rmagent/cases.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

CASES = Path.home() / ".rmagent" / "cases"
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9]{8,}|Bearer\s+\S+|api[_-]?key\s*=\s*\S+)", re.I)


def _scrub(obj):
    s = json.dumps(obj, default=str)
    s = SECRET_RE.sub("<redacted>", s)
    try:
        return json.loads(s)
    except Exception:
        return obj


def _write(case_dir: Path, name: str, obj) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    p = case_dir / name
    if name.endswith(".jsonl"):
        with p.open("a") as f:
            f.write(json.dumps(_scrub(obj), default=str) + "\n")
        return
    data = []
    if p.exists():
        try:
            data = json.loads(p.read_text() or "[]")
        except Exception:
            data = []
    data.append(_scrub(obj))
    p.write_text(json.dumps(data, indent=2, default=str))


def _smoke(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    agents = data.get("agents") or data.get("processes") or data.get("harnesses") or []
    return bool(agents) or bool(data.get("shadow")) or bool(data.get("endpoints"))


def main():
    ap = argparse.ArgumentParser(description="RMAgent AO hunt")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--since", default="2h")
    ap.add_argument("--case-dir")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()
    since_h = 2.0
    s = args.since.strip().lower()
    if s.endswith("h"):
        since_h = float(s[:-1] or 2)
    else:
        try:
            since_h = float(s)
        except ValueError:
            since_h = 2.0
    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    case_dir = Path(args.case_dir) if args.case_dir else (CASES / time.strftime("ao-%Y%m%d-%H%M%S"))
    case_dir.mkdir(parents=True, exist_ok=True)
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[ao-hunt {t}] {len(rows)} → {case_dir}")
    follow = ("agentstate", "agenttrace", "agentnet")
    for row in rows:
        wid = row.get("id")
        if "agents" not in (row.get("skills") or ["agents"]):
            continue
        res = lib.ask(row, "agents", since_hours=since_h, limit=args.limit)
        if hasattr(lib, "record_ask"):
            lib.record_ask(case_dir, row, "agents", res)
        data = _scrub(res.get("data") or {})
        smoke = res.get("ok") and _smoke(data if isinstance(data, dict) else {})
        _write(case_dir, "path.json", {"witness": wid, "question": "agents",
                                       "ok": res.get("ok"), "smoke": smoke, "hole": res.get("hole")})
        print(f"  {wid:8} agents ok={res.get('ok')} smoke={smoke}")
        if not smoke:
            continue
        for q in follow:
            if q not in (row.get("skills") or follow):
                continue
            r2 = lib.ask(row, q, since_hours=since_h, limit=args.limit)
            if hasattr(lib, "record_ask"):
                lib.record_ask(case_dir, row, q, r2)
            _write(case_dir, "path.json", {"witness": wid, "question": q, "ok": r2.get("ok"),
                                           "hole": r2.get("hole")})
            print(f"  {wid:8} {q:12} ok={r2.get('ok')}")
    print(f"wrote {case_dir}")


if __name__ == "__main__":
    main()
