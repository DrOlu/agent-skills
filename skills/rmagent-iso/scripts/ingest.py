#!/usr/bin/env python3
"""Door: tshark hex TCP payloads → PAN-masked ring records.

This is NOT a question. Hunt never calls tshark. A sensor process does.

    tshark -i eth1 -l -T fields -e frame.time_epoch -e ip.src -e tcp.srcport \
           -e ip.dst -e tcp.dstport -e tcp.payload \
      | python3 ingest.py --tap tap-fep-cba --ring /var/rmagent-iso/rings/tap-fep-cba.jsonl

tcp.payload is hex without colons. Private headers (length prefix, TPDU)
must be stripped by --skip-bytes if present.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from decode import unpack_record
from ring import Ring


def ingest_line(line: str, *, tap: str, skip_bytes: int = 0) -> dict | None:
    parts = line.strip().split("\t")
    if len(parts) < 6:
        return None
    try:
        t = float(parts[0])
    except ValueError:
        return None
    src = f"{parts[1]}:{parts[2]}"
    dst = f"{parts[3]}:{parts[4]}"
    hexpay = parts[5].replace(":", "").strip()
    if not hexpay:
        return None
    try:
        buf = bytes.fromhex(hexpay)
    except ValueError:
        return None
    if skip_bytes:
        buf = buf[skip_bytes:]
    try:
        return unpack_record(buf, tap=tap, t=t, src=src, dst=dst)
    except Exception:
        return {"t": t, "tap": tap, "src": src, "dst": dst, "hole": True, "reason": "decode-error"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap", required=True)
    ap.add_argument("--ring", required=True)
    ap.add_argument("--skip-bytes", type=int, default=0)
    args = ap.parse_args(argv)
    ring = Ring(args.ring)
    ring.init()
    n_ok = n_err = 0
    for line in sys.stdin:
        rec = ingest_line(line, tap=args.tap, skip_bytes=args.skip_bytes)
        if rec is None:
            continue
        if rec.get("hole"):
            n_err += 1
            continue  # decode errors are counted, not stored (no lake of garbage)
        ring.append(rec)
        n_ok += 1
    print(f"ingested ok={n_ok} decode_error={n_err} tap={args.tap}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
