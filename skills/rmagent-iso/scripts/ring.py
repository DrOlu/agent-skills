#!/usr/bin/env python3
"""Circular JSONL ring — bounded, overwrite-oldest, never a PCAP lake.

Each line is one already-decoded, PAN-masked ISO record. When the file exceeds
max_bytes, the oldest lines are dropped on the next append (or on compact()).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from iso import MAX_PULL_BYTES, assert_no_pan

DEFAULT_MAX_BYTES = 64 * 1024 * 1024  # 64 MiB


class Ring:
    def __init__(self, path: Path | str, max_bytes: int = DEFAULT_MAX_BYTES):
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        if not self.path.exists():
            self.path.write_text("")

    def append(self, rec: dict[str, Any]) -> None:
        assert_no_pan(rec)
        line = json.dumps(rec, separators=(",", ":")) + "\n"
        with self.path.open("a") as f:
            f.write(line)
        if self.path.stat().st_size > self.max_bytes:
            self.compact()

    def compact(self) -> None:
        """Drop oldest lines until under 80% of max_bytes."""
        if not self.path.exists():
            return
        target = int(self.max_bytes * 0.8)
        data = self.path.read_bytes()
        if len(data) <= target:
            return
        # keep a suffix
        cut = len(data) - target
        nl = data.find(b"\n", cut)
        kept = data[nl + 1:] if nl != -1 else data[-target:]
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_bytes(kept)
        tmp.replace(self.path)

    def read(self, since: float | None = None, limit: int | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if since is not None and (rec.get("t") or 0) < since:
                    continue
                out.append(rec)
                if limit is not None and len(out) >= limit:
                    break
        return out

    def stats(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "path": str(self.path),
                "exists": False,
                "bytes": 0,
                "n": 0,
                "oldest_t": None,
                "newest_t": None,
                "blind": True,
                "blind_reason": "ring-missing",
            }
        recs = self.read()
        ts = [r.get("t") for r in recs if r.get("t") is not None]
        return {
            "path": str(self.path),
            "exists": True,
            "bytes": self.path.stat().st_size,
            "max_bytes": self.max_bytes,
            "n": len(recs),
            "oldest_t": min(ts) if ts else None,
            "newest_t": max(ts) if ts else None,
            "age_s": (time.time() - max(ts)) if ts else None,
            "blind": len(recs) == 0,
            "blind_reason": "empty" if not recs else None,
        }


def load_all(ring_dir: Path | str, since: float | None = None) -> list[dict]:
    d = Path(ring_dir)
    recs: list[dict] = []
    if not d.exists():
        return recs
    for p in sorted(d.glob("*.jsonl")):
        recs.extend(Ring(p).read(since=since))
    recs.sort(key=lambda r: (r.get("t") or 0, r.get("tap") or ""))
    return recs


def cmd_init(dirpath: str, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    d = Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    for name in ("tap-fep-acq.jsonl", "tap-fep-cba.jsonl", "tap-term-ej.jsonl"):
        Ring(d / name, max_bytes=max_bytes).init()
    print(f"rings ready under {d} max_bytes={max_bytes}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--dir", required=True)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = ap.parse_args()
    if args.cmd == "init":
        cmd_init(args.dir, args.max_bytes)
