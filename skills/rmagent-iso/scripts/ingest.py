#!/usr/bin/env python3
"""Door: tshark hex TCP payloads → PAN-masked ring records.

This is NOT a question. Hunt never calls tshark. A sensor process does.

    tshark -i eth1 -l -T fields -e frame.time_epoch -e ip.src -e tcp.srcport \
           -e ip.dst -e tcp.dstport -e tcp.payload \
      | python3 ingest.py --tap tap-fep-cba --ring /var/rmagent-iso/rings/tap-fep-cba.jsonl

tcp.payload is hex without colons. Private headers (length prefix, TPDU)
must be stripped by --skip-bytes if present.

REV 20 (P0): tcp.payload segments are STREAM SLICES, not ISO messages. Each
segment is now fed through a bounded per-flow reassembler (reasm.py) before
decoding, so:
  - a message split across segments decodes once complete (was: decode hole);
  - coalesced messages are split and BOTH are recorded (was: only the first);
  - buffers are hard-bounded (1 MiB/flow, 256 flows, 120 s idle) and every
    dropped byte is counted — bounded memory, never a silent loss.
Reassembly stats are printed at exit so "N decode errors" is explainable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from decode import unpack_record
from ring import Ring
from reasm import Reassembler


def ingest_line(line: str, *, tap: str, skip_bytes: int = 0,
                reasm: Reassembler | None = None) -> list[dict]:
    """One tshark line -> list of ring records (0..n; coalescing splits)."""
    parts = line.strip().split("\t")
    if len(parts) < 6:
        return []
    try:
        t = float(parts[0])
    except ValueError:
        return []
    src = f"{parts[1]}:{parts[2]}"
    dst = f"{parts[3]}:{parts[4]}"
    hexpay = parts[5].replace(":", "").strip()
    if not hexpay:
        return []
    try:
        buf = bytes.fromhex(hexpay)
    except ValueError:
        return []
    if skip_bytes:
        buf = buf[skip_bytes:]

    messages = [buf]
    if reasm is not None:
        messages, _flushes = reasm.feed(src, dst, buf)
        if _flushes:
            return [{"t": t, "tap": tap, "src": src, "dst": dst, "hole": True,
                     "reason": _flushes[0]}]

    out = []
    for msg in messages:
        try:
            out.append(unpack_record(msg, tap=tap, t=t, src=src, dst=dst))
        except Exception:
            out.append({"t": t, "tap": tap, "src": src, "dst": dst,
                        "hole": True, "reason": "decode-error"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap", required=True)
    ap.add_argument("--ring", required=True)
    ap.add_argument("--skip-bytes", type=int, default=0)
    ap.add_argument("--no-reasm", action="store_true",
                    help="disable per-flow reassembly (legacy segment mode)")
    args = ap.parse_args(argv)
    ring = Ring(args.ring)
    ring.init()
    reasm = None if args.no_reasm else Reassembler()
    n_ok = n_err = 0
    for line in sys.stdin:
        for rec in ingest_line(line, tap=args.tap, skip_bytes=args.skip_bytes,
                               reasm=reasm):
            if rec.get("hole"):
                n_err += 1
                continue  # decode errors are counted, not stored (no lake of garbage)
            ring.append(rec)
            n_ok += 1
    print(f"ingested ok={n_ok} decode_error={n_err} tap={args.tap}", file=sys.stderr)
    if reasm is not None:
        s = reasm.stats
        print(f"reasm segments={s['segments']} flows={s['flows_seen']} "
              f"flushed={s['flows_flushed']} dropped_bytes={s['bytes_dropped']} "
              f"pending={reasm.pending_bytes()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
