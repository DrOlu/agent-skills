#!/usr/bin/env python3
"""Bounded per-flow TCP reassembly for the ISO tap (REV 20).

tcp.payload from tshark is stream SEGMENTS, not ISO messages: one message can
be split across segments, and several messages can be coalesced into one.
ingest.py used to decode each segment independently — fragmented messages
decoded as holes and coalesced ones lost all but the first message.

This module reassembles per (src, dst) flow with hard bounds:

  - MAX_FLOW_BYTES per buffered flow (default 1 MiB) — a stuck flow is
    flushed and counted, never allowed to grow.
  - MAX_FLOWS concurrent flows (default 256) — the oldest flow is evicted.
  - IDLE_TIMEOUT seconds — idle flows are flushed.

The buffer holds RAW PAYLOAD BYTES on the sensor only (transient, bounded);
decoded + PAN-masked records are the only thing that ever reaches the ring.
"""

from __future__ import annotations

import time
from collections import OrderedDict

MAX_FLOW_BYTES = 1 * 1024 * 1024
MAX_FLOWS = 256
IDLE_TIMEOUT = 120.0


def _iso_consumed_length(buf: bytes) -> int | None:
    """How many bytes one ASCII ISO 8583 message starting at buf[0] spans.

    Mirrors decode.py's field specs: MTI(4) + bitmap(8, +8 if secondary) +
    each present field's encoded length. Returns None when the message is
    structurally invalid (not enough header bytes) — the caller then treats
    the bytes as preamble.
    """
    from decode import FIELDS, _bit_on

    if len(buf) < 12:
        return None
    i = 4  # MTI
    bm1 = buf[i:i + 8]
    i += 8
    bitmap = bytearray(bm1)
    if _bit_on(bm1, 1):
        if len(buf) < i + 8:
            return None
        bitmap += buf[i:i + 8]
        i += 8
    max_field = 128 if len(bitmap) == 16 else 64
    for f in range(2, max_field + 1):
        if not _bit_on(bytes(bitmap), f):
            continue
        spec = FIELDS.get(f)
        if spec is None:
            # unknown present field — layout unknown, cannot frame safely
            return None
        length, _kind = spec
        if length == "ll":
            if len(buf) < i + 2:
                return None
            try:
                n = int(buf[i:i + 2].decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                return None
            i += 2
            if len(buf) < i + n:
                return None
            i += n
        elif length == "lll":
            if len(buf) < i + 3:
                return None
            try:
                n = int(buf[i:i + 3].decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                return None
            i += 3
            if len(buf) < i + n:
                return None
            i += n
        else:
            if len(buf) < i + length:
                return None
            i += length
    return i


class Reassembler:
    """Per-flow reassembly keyed by (src, dst). `feed()` returns any
    messages that became decodable (whole lines ending in our framing
    heuristic: an ASCII ISO message is emitted when the accumulated buffer
    parses, or on delimiter heuristics delegated to the caller)."""

    def __init__(self, max_flow_bytes: int = MAX_FLOW_BYTES,
                 max_flows: int = MAX_FLOWS,
                 idle_timeout: float = IDLE_TIMEOUT):
        self.max_flow_bytes = max_flow_bytes
        self.max_flows = max_flows
        self.idle_timeout = idle_timeout
        self._flows: OrderedDict[str, dict] = OrderedDict()
        self.stats = {"flows_seen": 0, "flows_flushed": 0,
                      "bytes_dropped": 0, "segments": 0}

    def _evict_oldest(self) -> None:
        while len(self._flows) >= self.max_flows:
            _, f = self._flows.popitem(last=False)
            self.stats["flows_flushed"] += 1
            self.stats["bytes_dropped"] += len(f["buf"])

    def feed(self, src: str, dst: str, payload: bytes, now: float | None = None):
        """Feed one segment; return (messages, flush_reasons).

        Messages are byte strings whose framing the CALLER decodes
        (decode.py / unpack_record). We only split; we never interpret.
        Splitting rule: ISO 8583 ASCII messages are length-prefixed or
        delimited per dialect, so the reassembler hands the caller the
        accumulated buffer whenever a candidate boundary is found:
        an MTI-looking 'XXXX' + bitmap start. The caller retries decode;
        on failure the bytes stay buffered for the next segment.
        """
        now = now if now is not None else time.time()
        self.stats["segments"] += 1
        key = f"{src}>{dst}"
        flow = self._flows.get(key)
        if flow is None:
            self._evict_oldest()
            flow = {"buf": bytearray(), "t": now}
            self._flows[key] = flow
            self.stats["flows_seen"] += 1
        flow["t"] = now
        # move to most-recent
        self._flows.move_to_end(key)
        flow["buf"].extend(payload)
        if len(flow["buf"]) > self.max_flow_bytes:
            drop = len(flow["buf"])
            flow["buf"] = bytearray()
            self.stats["flows_flushed"] += 1
            self.stats["bytes_dropped"] += drop
            return [], ["flow-over-limit"]

        # idle flush of OTHER stale flows
        stale = [k for k, f in self._flows.items()
                 if now - f["t"] > self.idle_timeout]
        for k in stale:
            _, f = self._flows.pop(k)
            self.stats["flows_flushed"] += 1
            self.stats["bytes_dropped"] += len(f["buf"])

        return self._extract(key, flow), []

    def _extract(self, key: str, flow: dict) -> list[bytes]:
        """Pull decodable messages out of the flow buffer.

        REV 20, corrected: a plain "longest decodable prefix" heuristic is
        UNSOUND for ISO 8583 — a truncated buffer can still decode because
        unpack only reads fields whose bitmap bits are on, so a short prefix
        looks like a valid (wrong) message. Instead we determine the message
        LENGTH from the decoded field layout itself:

          1. find a candidate start (an MTI-looking 4 bytes)
          2. unpack the remaining buffer FROM that start (bit fields are
             self-describing) and compute how many bytes unpack actually
             consumed (mirroring the same field specs)
          3. emit exactly those bytes; repeat for the rest of the buffer

        A message is emitted only when its computed length fits inside the
        buffered bytes; otherwise we wait for more segments.
        """
        buf = flow["buf"]
        MTIS = (b"0200", b"0210", b"0400", b"0410", b"0420", b"0430",
                b"0800", b"0810")
        out: list[bytes] = []
        while True:
            start = -1
            for i in range(len(buf) - 4 + 1):
                if bytes(buf[i:i + 4]) in MTIS:
                    start = i
                    break
            if start < 0:
                break
            if start > 0:
                self.stats["bytes_dropped"] += start
                del buf[:start]
            need = _iso_consumed_length(bytes(buf))
            if need is None or need > len(buf):
                # candidate exists but the message is not complete yet
                break
            out.append(bytes(buf[:need]))
            del buf[:need]
        return out

    def pending_bytes(self) -> int:
        return sum(len(f["buf"]) for f in self._flows.values())
