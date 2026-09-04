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
        # REV 18 (H4): the ticket is PERSISTED here so hunt.py can inherit it
        # — the old code accepted --ticket and dropped it, which made the
        # "one tape" join require passing --ticket to hunt as well (and it
        # was silently lost if you forgot).
        "ticket": getattr(args, "ticket", None),
        "trigger": getattr(args, "trigger", "manual"),
    }
    (d / "case.json").write_text(json.dumps(meta, indent=2))
    (d / "CASE.md").write_text(f"# {meta['title']}\n\nOpened {meta['opened']}\nTrack: {args.principal or 'Administrator, SYSTEM'}\n"
                               + (f"Ticket: {meta['ticket']}\n" if meta['ticket'] else ""))
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


def cmd_prune(args):
    """Rev 17 (L3): a lake by accretion is still a lake.

    Old case dirs accumulate answers/*.json (full 32 KB pulls per witness per
    question) forever. Prune keeps the CASE STORY (CASE.md, case.json,
    correlation.json, holes.jsonl, path.json, trajectory.jsonl) and sheds the
    bulky raw answers of cases older than the cutoff. Nothing newer than
    --days is ever touched; --dry-run shows what would go.
    """
    import shutil
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc).timestamp() - args.days * 86400
    root = Path(args.cases_dir)
    if not root.exists():
        print("(no cases dir)")
        return
    removed_files, removed_bytes, kept_cases = 0, 0, 0
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        # age by case.json's opened timestamp (fallback: dir mtime)
        ts = None
        try:
            meta = json.loads((d / "case.json").read_text())
            ts = datetime.fromisoformat((meta.get("opened") or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = d.stat().st_mtime
        if ts >= cutoff:
            kept_cases += 1
            continue
        adir = d / "answers"
        if adir.exists():
            if args.dry_run:
                n = len(list(adir.glob("*.json")))
                sz = sum(p.stat().st_size for p in adir.glob("*.json"))
                print(f"  [dry-run] {d.name}: would remove {n} answer file(s) ({sz//1024} KB)")
            else:
                shutil.rmtree(adir)
                removed_files += 1
                removed_bytes += 0
                print(f"  pruned {d.name}/answers (story kept)")
    if args.dry_run:
        print("(dry run — nothing removed; re-run without --dry-run)")
    else:
        print(f"pruned answers/ from {removed_files} old case(s); {kept_cases} recent case(s) untouched")


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
    p = sub.add_parser("prune", help="shed old cases' raw answers (keep the story)")
    p.add_argument("--days", type=int, default=30, help="cases older than this are pruned (default 30)")
    p.add_argument("--cases-dir", default="./cases")
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "open":
        cmd_open(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "close":
        cmd_close(args)
    elif args.cmd == "prune":
        cmd_prune(args)


if __name__ == "__main__":
    main()
