#!/usr/bin/env python3
"""OTel span emission — meet the APM world where it is.

RMAgent traces become first-class citizens of the existing observability stack
(Grafana/Jaeger/Splunk) instead of a parallel universe. Spans are tiny and
derived from data we already have. Cost: near zero.

Each trajectory entry becomes one OTel span:
  traceId  = STC case id (32 hex)
  spanId   = trajectory entry id (16 hex)
  parentSpanId = trajectory parent entry id
  name     = rmagent.{skill}.{witness}

Emission is best-effort: if the RTerm gateway is unreachable, spans are buffered
to disk and flushed on the next successful emission. Never blocks a hunt.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

# REV 18 (H5): the gateway endpoint is CONFIGURABLE, not hard-coded. The old
# value (http://127.0.0.1:8765) pointed at a port nothing listens on — every
# span this skill ever emitted went to the disk buffer and died there (326
# buffered, zero delivered when found). Resolution order:
#   1. env RMAgent_OTEL_URL
#   2. ~/.rmagent/config.json {"otel_gateway_url": "..."}
#   3. default: the RTerm gateway on 17888
def _gateway_url() -> str:
    u = os.environ.get("RMAgent_OTEL_URL")
    if u:
        return u.rstrip("/")
    try:
        cfg = Path.home() / ".rmagent" / "config.json"
        if cfg.exists():
            import json as _j
            u = (_j.loads(cfg.read_text()) or {}).get("otel_gateway_url")
            if u:
                return u.rstrip("/")
    except Exception:
        pass
    return "http://127.0.0.1:17888"

# Optional auth header value (env or config "otel_gateway_token"). Empty by
# default; a gateway that needs auth will 401 and the emit is buffered.
def _gateway_token() -> str:
    t = os.environ.get("RMAgent_OTEL_TOKEN")
    if t:
        return t
    try:
        cfg = Path.home() / ".rmagent" / "config.json"
        if cfg.exists():
            import json as _j
            t = (_j.loads(cfg.read_text()) or {}).get("otel_gateway_token")
            if t:
                return t
    except Exception:
        pass
    return ""

BUFFER = Path.home() / ".rmagent" / "otel_spans.jsonl"
BUFFER_MAX = 500


def span_from_entry(entry: dict, stc) -> dict:
    """Build one OTel span from a trajectory entry + its STC."""
    t = entry.get("t", "")
    ts = _iso_to_nano(t) or int(time.time() * 1e9)
    dur_ns = int(0)  # observations are instantaneous; duration filled by the caller if known
    return {
        "traceId": stc.trace_id,
        "spanId": stc.span_id(entry.get("id", 0)),
        "parentSpanId": stc.span_id(entry.get("parent") or 0) if entry.get("parent") else None,
        "name": f"rmagent.{entry.get('skill') or 'think'}.{entry.get('witness') or 'case'}",
        "kind": "SPAN_KIND_INTERNAL",
        "startTimeUnixNano": ts,
        "endTimeUnixNano": ts + dur_ns,
        "status": {"code": "ERROR" if entry.get("kind") == "hole" else "OK"},
        "attributes": {
            "rmagent.kind": entry.get("kind", "?"),
            "rmagent.branch": entry.get("branch", "main"),
            "rmagent.principal": stc.principal,
            "rmagent.case": stc.case,
            "rmagent.depth": stc.depth,
            "rmagent.content": str(entry.get("content", ""))[:200],
            # enrichment: why this hunt exists, and what business object it touches
            "rmagent.trigger": getattr(stc, "trigger", "manual"),
            "rmagent.ticket": getattr(stc, "ticket", None) or "",
            # v2: the request-level join. When set, this span can be correlated
            # with the APPLICATION's own OTel trace in Grafana/Jaeger — one
            # waterfall showing both the app request and the security walk.
            "rmagent.app_trace_id": getattr(stc, "app_trace_id", None) or "",
        },
    }


def emit(spans: list[dict]) -> bool:
    """Emit spans as an OTLP/HTTP-JSON payload. Best-effort; buffers on failure."""
    if not spans:
        return True
    payload = {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "rmagent"}},
                {"key": "service.version", "value": {"stringValue": "rev6"}},
            ]},
            "scopeSpans": [{"scope": {"name": "rmagent.observatory"}, "spans": spans}],
        }]
    }
    ok = _post(payload)
    if not ok:
        _buffer(spans)
    # opportunistic flush of anything previously buffered
    _flush_buffered()
    return ok


def _post(payload: dict) -> bool:
    """POST to the gateway's OTLP/HTTP-JSON ingest endpoint. Never raises.
    H5: uses the configurable gateway URL and optional bearer token."""
    try:
        import urllib.request
        headers = {"Content-Type": "application/json"}
        tok = _gateway_token()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request(
            f"{_gateway_url()}/api/apm/ingest",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _buffer(spans: list[dict]) -> None:
    try:
        BUFFER.parent.mkdir(parents=True, exist_ok=True)
        with BUFFER.open("a") as f:
            for s in spans:
                f.write(json.dumps(s) + "\n")
        lines = BUFFER.read_text().splitlines()
        if len(lines) > BUFFER_MAX:
            BUFFER.write_text("\n".join(lines[-BUFFER_MAX:]) + "\n")
    except OSError:
        pass


def _flush_buffered() -> None:
    if not BUFFER.exists():
        return
    try:
        lines = BUFFER.read_text().splitlines()
        if not lines:
            return
        spans = []
        for line in lines:
            try:
                spans.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if spans and _post(_wrap(spans)):
            BUFFER.unlink()  # flushed successfully — clear the buffer
    except OSError:
        pass


def _wrap(spans: list[dict]) -> dict:
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "rmagent"}},
            ]},
            "scopeSpans": [{"scope": {"name": "rmagent.observatory"}, "spans": spans}],
        }]
    }


def _iso_to_nano(iso: str) -> int | None:
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1e9)
    except (ValueError, TypeError):
        return None
