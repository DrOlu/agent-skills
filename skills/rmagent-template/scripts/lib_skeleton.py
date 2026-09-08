#!/usr/bin/env python3
"""Copy-me engine: allowlisted ask(), 32 KB cap, holes, no actuate.

This file is a skeleton. new_skill.py copies it to scripts/lib.py and
rewrites ALLOWED. Doors (ssh/winrm/ring) are stubs — fill from
rmagent-so/lib.py or rmagent-iso/lib.py.
"""
from __future__ import annotations

import json
from typing import Any

ALLOWED = {"attest", "sketch", "edges", "explain", "trace", "hops", "fail", "baseline"}
MAX_PULL_BYTES = 32 * 1024
WALK_DEPTH = 8
WALK_FANOUT = 3
COOLDOWN_SEC = 300
BASELINE_MIN_N = 30


def cap(obj: Any, limit: int = MAX_PULL_BYTES) -> tuple[Any, bool]:
    raw = json.dumps(obj, default=str)
    n = len(raw.encode("utf-8"))
    if n <= limit:
        return obj, False
    return {
        "hole": True,
        "reason": "capped",
        "bytes": n,
        "limit": limit,
        "note": "answer exceeded cap; not stored. tighten window or limit.",
    }, True


def hole(asked: str, why: str, **extra: Any) -> dict[str, Any]:
    out = {"hole": True, "asked": asked, "empty": True, "why": why}
    out.update(extra)
    return out


def ask(question: str, **params: Any) -> dict[str, Any]:
    q = (question or "").strip()
    if q == "actuate" or q not in ALLOWED:
        return hole(q or "?", "not-allowlisted", reason="not-allowlisted", question=q)
    # Domain implementations replace this dispatcher.
    handlers = {
        "attest": _attest,
        "sketch": _not_implemented,
        "edges": _not_implemented,
        "explain": _not_implemented,
        "trace": _not_implemented,
        "hops": _not_implemented,
        "fail": _not_implemented,
        "baseline": _baseline_guard,
    }
    fn = handlers.get(q, _not_implemented)
    ans = fn(q, **params)
    out, capped = cap(ans)
    return out if not capped else out


def _attest(question: str, **params: Any) -> dict[str, Any]:
    """Sightedness first. REPLACE with a real door before trusting anything.

    REV 20: the skeleton used to return ok=True with blind_check='unknown' —
    a stub that looked like a sighted witness. A scaffold must NEVER claim
    success. Unimplemented = hole, honestly."""
    return {
        "hole": True,
        "asked": question,
        "empty": True,
        "why": "not-implemented (scaffold): wire a real door + blind_check "
               "before any question is trusted",
    }


def _baseline_guard(question: str, **params: Any) -> dict[str, Any]:
    n = int(params.get("n") or 0)
    if n < BASELINE_MIN_N:
        return hole(
            "baseline",
            "baseline-n-too-small",
            reason="baseline-n-too-small",
            n=n,
            need=BASELINE_MIN_N,
            note="same floor as rmagent thinker. do not call n<30 'normal'.",
        )
    return {"question": "baseline", "hole": False, "n": n, "note": "fill percentiles"}


def _not_implemented(question: str, **params: Any) -> dict[str, Any]:
    return hole(question, "not-implemented", reason="not-implemented")
