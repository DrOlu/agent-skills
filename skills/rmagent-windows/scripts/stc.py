#!/usr/bin/env python3
"""Security Trace Context (STC) — the W3C Trace Context analog for security ops.

Propagates context (not data) across hosts and cases. Like `traceparent`, but the
unit is a principal's walk across an estate, not a request across services.

    stc: case=CASE-20260825-143022; principal=Administrator; window=2h; origin=jh1; depth=2

Rules:
  - Context propagates; event data never does (the no-lake rule).
  - depth is the distributed circuit breaker: the walk budget (depth <= 8) applies
    across the WHOLE trace, not per-host. This is what stops the hunter becoming a worm.
  - Every correlation must be reconstructable from the trajectory alone.
"""
from __future__ import annotations
from dataclasses import dataclass, replace, field
import time

MAX_DEPTH = 8          # the walk budget — same as the hunt budget, now distributed
MAX_FANOUT = 3         # max children spawned from one hop


@dataclass(frozen=True)
class STC:
    """Security Trace Context. Immutable; child() returns a new one at depth+1.

    ticket: an optional business identifier (payment id, incident number, change
    reference). This is the Flight Recorder join — the same tape serves security
    ("who walked?") and reliability ("why did it feel slow?").
    trigger: what started this hunt (scheduled | alert | manual | drill | backfill).
    Propagated so a human reading the trace months later knows the context.
    """
    case: str
    principal: str
    window_h: float = 2.0
    origin: str = "jh1"
    depth: int = 0
    fanout: int = 0
    ticket: str | None = None
    trigger: str = "manual"

    # ---------------------------------------------------------------- encode
    def encode(self) -> str:
        out = (f"case={self.case}; principal={self.principal}; "
               f"window={self.window_h}h; origin={self.origin}; depth={self.depth}")
        if self.ticket:
            out += f"; ticket={self.ticket}"
        if self.trigger and self.trigger != "manual":
            out += f"; trigger={self.trigger}"
        return out

    @classmethod
    def decode(cls, s: str) -> "STC":
        """Parse an encoded STC. Raises ValueError on malformed input."""
        parts = {}
        for tok in s.replace("stc:", "").split(";"):
            tok = tok.strip()
            if "=" in tok:
                k, v = tok.split("=", 1)
                parts[k.strip()] = v.strip()
        if "case" not in parts or "principal" not in parts:
            raise ValueError(f"STC missing case/principal: {s!r}")
        w = parts.get("window", "2h")
        window = float(w.rstrip("h")) if w else 2.0
        return cls(
            case=parts["case"],
            principal=parts["principal"],
            window_h=window,
            origin=parts.get("origin", "jh1"),
            depth=int(parts.get("depth", "0")),
            ticket=parts.get("ticket") or None,
            trigger=parts.get("trigger", "manual"),
        )

    # ---------------------------------------------------------------- lineage
    def child(self) -> "STC":
        """A child context for the next host in the walk. depth+1."""
        if self.depth + 1 > MAX_DEPTH:
            raise ValueError(f"STC depth budget exhausted ({self.depth} >= {MAX_DEPTH})")
        return replace(self, depth=self.depth + 1)

    def sibling(self) -> "STC":
        """A sibling context for a parallel branch (same depth, fanout+1)."""
        if self.fanout + 1 > MAX_FANOUT:
            raise ValueError(f"STC fanout budget exhausted ({self.fanout} >= {MAX_FANOUT})")
        return replace(self, fanout=self.fanout + 1)

    # ---------------------------------------------------------------- budget
    @property
    def can_descend(self) -> bool:
        return self.depth < MAX_DEPTH

    @property
    def can_fanout(self) -> bool:
        return self.fanout < MAX_FANOUT

    # ---------------------------------------------------------------- ids
    @property
    def trace_id(self) -> str:
        """OTel-compatible trace id (32 hex chars) derived from the case id."""
        return self.case.replace("-", "").replace("_", "")[:32].ljust(32, "0")

    def span_id(self, entry_id: int) -> str:
        """OTel-compatible span id (16 hex chars) derived from a trajectory entry id."""
        return f"{entry_id:016x}"[-16:]

    # ---------------------------------------------------------------- display
    def __str__(self) -> str:
        return self.encode()


def new_case_id(prefix: str = "CASE") -> str:
    """Generate a case id like CASE-20260825-143022."""
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"
