#!/usr/bin/env python3
"""Case — open / list / close a one-page hunt case.

A case is a folder with: CASE.md (readable), path.json (hops),
holes.jsonl, asks.jsonl. Megabytes, not a dump. No Event Log lives here.

Usage:
  python3 case.py open --title "admin walk" --principal Administrator
  python3 case.py list
  python3 case.py close ./cases/admin-walk
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

CASES = Path("./cases")


def cmd_open(args):
    CASES.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    d = CASES / f"{args.slug or ts}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "path.json").write_text("[]")
    meta = {
        "title": args.title or "untitled", "principal": args.principal,
        "opened": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": 0, "actuate": False,
    }
    (d / "case.json").write_text(json.dumps(meta, indent=2))
    (d / "CASE.md").write_text(f"# {meta['title']}\n\nOpened {meta['opened']}\nTrack: {args.principal or 'Administrator, SYSTEM'}\n")
    print(str(d.resolve()))


def cmd_list(args):
    if not CASES.exists():
        print("(no cases)")
        return
    for d in sorted(CASES.iterdir()):
        if d.is_dir():
            meta = {}
            try:
                meta = json.loads((d / "case.json").read_text())
            except Exception:
                pass
            holes = 0
            hf = d / "holes.jsonl"
            if hf.exists():
                holes = sum(1 for l in hf.read_text().splitlines() if l.strip())
            print(f"{d.name:24} {meta.get('title', '')[:40]:40} holes={holes}")


def cmd_close(args):
    d = Path(args.dir)
    meta_path = d / "case.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass
    meta["closed"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_path.write_text(json.dumps(meta, indent=2))
    with (d / "CASE.md").open("a") as f:
        f.write(f"\nClosed {meta['closed']}\n")
    print(f"closed {d}")


def main():
    ap = argparse.ArgumentParser(description="RMAgent case writer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("--title", required=True)
    o.add_argument("--principal", default="Administrator")
    o.add_argument("--slug")
    o.add_argument("--ticket", default=None, help="business ticket (payment id, incident number) — the Flight Recorder join")
    o.add_argument("--trigger", default="manual", choices=["manual","scheduled","alert","drill","backfill"], help="what started this hunt")
    sub.add_parser("list")
    c = sub.add_parser("close")
    c.add_argument("dir")
    args = ap.parse_args()
    if args.cmd == "open":
        cmd_open(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "close":
        cmd_close(args)


if __name__ == "__main__":
    main()
