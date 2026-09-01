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
    # v2 (request-level join): the application-level trace id (OTel trace_id /
    # W3C traceparent) observed on a witness. Lets ONE case serve both lenses
    # — "who walked?" (principal) AND "which request was slow?" (app trace).
    # Identity-led and request-led correlation on the same tape.
    app_trace_id: str | None = None

    def __post_init__(self):
        # INJECTION FIX: the STC is a delimiter-based format ("; k=v"). A ticket
        # or trigger containing ';' or '=' can inject/override arbitrary fields
        # on decode — including principal and depth (the walk budget). Reject
        # them at construction rather than trying to escape.
        for field_name in ("ticket", "trigger", "case", "principal", "origin",
                            "app_trace_id"):
            v = getattr(self, field_name, None)
            if v and (";" in str(v) or "=" in str(v)):
                raise ValueError(
                    f"STC {field_name} contains the delimiter ';' or '=' and "
                    f"would corrupt the trace context: {v!r}")

    # ---------------------------------------------------------------- encode
    def encode(self) -> str:
        out = (f"case={self.case}; principal={self.principal}; "
               f"window={self.window_h}h; origin={self.origin}; depth={self.depth}")
        if self.ticket:
            out += f"; ticket={self.ticket}"
        if self.app_trace_id:
            out += f"; apptrace={self.app_trace_id}"
        if self.trigger and self.trigger != "manual":
            out += f"; trigger={self.trigger}"
        return out

    @classmethod
    def decode(cls, s: str) -> "STC":
        """Parse an encoded STC. Raises ValueError on malformed input.

        INJECTION FIX: duplicate keys are rejected. The attack is not
        delimiter-in-value (values are split cleanly) but KEY DUPLICATION —
        'case=C1; principal=Admin; ticket=X; principal=root; depth=9' has a
        clean ticket but principal appears twice and the last one wins. A
        crafted ticket could rewrite principal or depth (the walk budget).
        """
        parts = {}
        for tok in s.replace("stc:", "").split(";"):
            tok = tok.strip()
            if "=" in tok:
                k, v = tok.split("=", 1)
                k = k.strip()
                if k in parts:
                    raise ValueError(
                        f"STC duplicate key {k!r} — possible injection: {s!r}")
                parts[k] = v.strip()
        if "case" not in parts or "principal" not in parts:
            raise ValueError(f"STC missing case/principal: {s!r}")
        # INJECTION FIX: reject values containing the delimiters — a crafted
        # ticket like "X; principal=root; depth=9" would override fields
        for k in ("ticket", "trigger", "case", "principal", "origin", "apptrace"):
            v = parts.get(k)
            if v and (";" in v or "=" in v):
                raise ValueError(f"STC {k} contains delimiters: {v!r}")
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
            app_trace_id=parts.get("apptrace") or None,
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
