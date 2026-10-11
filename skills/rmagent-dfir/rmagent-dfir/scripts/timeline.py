#!/usr/bin/env python3
"""timeline.py — merge every case artifact into one super-timeline.

Walks answers/*.json and collected/*.json recursively, pulls anything that
looks like a timestamped record (keys t/utc/time/TimeCreated/CreationDate/
last/timestamp), normalizes to {ts, source, kind, text}, sorts, writes
timeline.jsonl (+ CSV). Holes and empty answers contribute nothing — an
absence in the timeline is honest.
"""
import csv, json, sys
from pathlib import Path

TS_KEYS = ("t", "utc", "time", "TimeCreated", "CreationDate", "CreationDateUtc",
           "timestamp", "last_boot", "mtime", "LastWriteTimeUtc")
TXT_KEYS = ("name", "detail", "message", "why", "kind", "path", "user", "exec",
            "task", "service", "group", "member", "file", "reason", "state",
            "local", "remote", "Device", "serial")

def _txt(d):
    parts = []
    for k in TXT_KEYS:
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            parts.append(f"{k}={v}")
    if not parts:
        parts.append(json.dumps({k: v for k, v in d.items()
                                 if k not in TS_KEYS}, default=str)[:120])
    return " ".join(parts)[:220]

def records(obj, source, acc):
    if isinstance(obj, dict):
        ts = next((obj[k] for k in TS_KEYS if obj.get(k)), None)
        if isinstance(ts, str) and len(ts) >= 10:
            kind = obj.get("skill") or obj.get("kind") or obj.get("Id") or obj.get("state") or "event"
            acc.append({"ts": ts, "source": source, "kind": str(kind)[:40],
                        "text": _txt(obj)})
        for v in obj.values():
            records(v, source, acc)
    elif isinstance(obj, list):
        for v in obj:
            records(v, source, acc)

def build(case: Path, out: str | None = None):
    case = Path(case)
    acc = []
    for f in sorted((case / "answers").glob("*.json")):
        try:
            records(json.load(open(f)), f"answer:{f.stem}", acc)
        except Exception:
            pass
    for f in sorted((case / "collected").glob("*.receipt.json")):
        try:
            r = json.load(open(f))
            if r.get("mtime_utc"):
                acc.append({"ts": r["mtime_utc"], "source": "acquired",
                            "kind": "file", "text": f"{r['path']} sha256={r['sha256_file'][:16]}"})
        except Exception:
            pass
    chain = case / "chain.jsonl"
    if chain.exists():
        for line in open(chain):
            try:
                e = json.loads(line)
                acc.append({"ts": e["t"], "source": "chain", "kind": e.get("kind", "?"),
                            "text": f"{e.get('witness','')} {e.get('question') or e.get('path') or ''}".strip()})
            except Exception:
                pass
    acc.sort(key=lambda x: x["ts"])
    out = out or str(case / "timeline.jsonl")
    with open(out, "w") as f:
        for r in acc:
            f.write(json.dumps(r) + "\n")
    with open(out.replace(".jsonl", ".csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "source", "kind", "text"])
        w.writeheader(); w.writerows(acc)
    return acc

if __name__ == "__main__":
    rows = build(Path(sys.argv[1] if len(sys.argv) > 1 else "cases/ir"))
    print(f"[timeline] {len(rows)} records")
