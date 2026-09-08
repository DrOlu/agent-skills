#!/usr/bin/env python3
"""ISO grain helpers — STAN/RRN keys, PAN masking, hop ids.

The grain is (stan, rrn) inside a time window. PAN is never a join key.
"""
from __future__ import annotations

from typing import Any

MAX_PULL_BYTES = 32 * 1024
BASELINE_MIN_N = 30
SLOW_THRESHOLD_MS = 800
CLOCK_SKEW_WARN_MS = 50
STAN_WINDOW_S = 120.0

SEGMENTS = ("A", "B", "C", "D", "E")


def mask_pan(pan: str) -> str:
    digits = "".join(c for c in pan if c.isdigit())
    if len(digits) < 10:
        return "*" * len(digits)
    return digits[:6] + ("*" * (len(digits) - 10)) + digits[-4:]


def grain(stan: str | None, rrn: str | None) -> str:
    s = (stan or "").strip().zfill(6) if stan else ""
    r = (rrn or "").strip()
    if not s and not r:
        raise ValueError("grain requires STAN or RRN")
    return f"stan={s or '-'};rrn={r or '-'}"


def key_of(rec: dict[str, Any]) -> str | None:
    stan = rec.get("stan")
    rrn = rec.get("rrn")
    if not stan and not rrn:
        return None
    try:
        return grain(stan, rrn)
    except ValueError:
        return None


def assert_no_pan(obj: Any) -> None:
    """Walk a structure; raise if a likely full PAN leaked."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in {"pan", "de2", "track2", "pinblock"}:
                raise ValueError(f"forbidden key {k!r} in ring/answer")
            assert_no_pan(v)
    elif isinstance(obj, list):
        for x in obj:
            assert_no_pan(x)
    elif isinstance(obj, str):
        digits = "".join(c for c in obj if c.isdigit())
        if 13 <= len(digits) <= 19 and "*" not in obj:
            # crude: 13-19 contiguous digits with no mask is a leak
            raise ValueError("possible raw PAN in answer")


def cap(obj: Any, limit: int = MAX_PULL_BYTES) -> tuple[Any, bool]:
    """JSON-size cap. Oversized → hole, never a truncated lie."""
    import json
    raw = json.dumps(obj, default=str)
    if len(raw.encode("utf-8")) <= limit:
        return obj, False
    return {
        "hole": True,
        "reason": "capped",
        "bytes": len(raw.encode("utf-8")),
        "limit": limit,
        "note": "answer exceeded cap; not stored. tighten --since or --limit.",
    }, True
