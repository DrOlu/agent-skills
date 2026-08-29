#!/usr/bin/env python3
"""Hop index — query across cases without a lake.

An index of POINTERS, not data. One line per hop, appended to
~/.rmagent/hop_index.jsonl. Kilobytes per case. Answers questions that were
impossible with per-case trajectories alone:

  - "All activity for LogonId 0x3a7f1c across all cases"  → grep the index
  - "Has this principal ever appeared before?"              → the memory the observatory lacked
  - "Which hosts did case X touch?"                         → index read, no WinRM at all

This is also the natural feed for the distributed thinker: "this LogonId was seen
on WS1 last Tuesday" is a correlation no single question can produce.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

INDEX = Path.home() / ".rmagent" / "hop_index.jsonl"
INDEX_MAX = 5000  # keep the last 5000 hops (plenty for a mid-size estate, months of cases)

HOP_KINDS = {"4624", "4648", "4672", "conn", "task", "service", "wmi", "file", "account", "hole"}


def record(case: str, entry_id: int, host: str, principal: str,
           logonid: str | None = None, hop_kind: str = "4624",
           t: str | None = None, detail: str = "",
           src_ip: str | None = None, sample: str = "full") -> dict:
    """Append one hop to the index. Returns the entry.

    sample: "full" records every field. "summary" records only the join keys
    (host, principal, kind, case) and drops logonid/src_ip/detail — used when a
    hunt found nothing, so the 5000-entry index window stretches from weeks to
    months. Suspicious hunts always record full.
    """
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    e = {
        "t": t or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "case": case,
        "entry": entry_id,
        "host": host,
        "principal": principal,
        "kind": hop_kind,
    }
    # BUG FIX: anything that is not explicitly "summary" records FULL fields.
    # Previously an invalid sample value fell into the else-branch and recorded
    # NEITHER full fields NOR the summary tag — silent data loss.
    if sample != "summary":
        e["logonid"] = logonid
        e["src_ip"] = src_ip
        e["detail"] = str(detail)[:200]
    else:
        e["sample"] = "summary"
    with INDEX.open("a") as f:
        f.write(json.dumps(e) + "\n")
    _trim()
    return e


def _trim() -> None:
    try:
        lines = INDEX.read_text().splitlines()
        if len(lines) > INDEX_MAX:
            INDEX.write_text("\n".join(lines[-INDEX_MAX:]) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- queries
def read_all() -> list[dict]:
    if not INDEX.exists():
        return []
    out = []
    for line in INDEX.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def by_logonid(logonid: str) -> list[dict]:
    """Every recorded hop for a LogonId, across all cases."""
    return [e for e in read_all() if e.get("logonid") == logonid]


def by_principal(principal: str) -> list[dict]:
    """Every recorded hop for a principal, across all cases."""
    return [e for e in read_all() if principal.lower() in str(e.get("principal", "")).lower()]


def by_case(case: str) -> list[dict]:
    """Every hop in one case."""
    return [e for e in read_all() if e.get("case") == case]


def by_host(host: str) -> list[dict]:
    """Every hop touching one host."""
    return [e for e in read_all() if e.get("host") == host]


def hosts_for_case(case: str) -> list[str]:
    """Which hosts a case touched — index read only, no WinRM."""
    return sorted({e["host"] for e in by_case(case) if e.get("host")})


def seen_before(host: str, principal: str, within_hours: float = 168) -> bool:
    """Has this principal ever been seen on this host recently (default: 7 days)?"""
    cutoff = time.time() - (within_hours * 3600)
    for e in by_principal(principal):
        if e.get("host") == host:
            try:
                from datetime import datetime, timezone
                et = datetime.fromisoformat(e["t"].replace("Z", "+00:00")).timestamp()
                if et >= cutoff:
                    return True
            except (ValueError, KeyError):
                continue
    return False


def render(entries: list[dict] | None = None) -> str:
    """Human-readable index rendering."""
    entries = entries if entries is not None else read_all()
    if not entries:
        return "(hop index is empty)"
    lines = []
    for e in entries:
        lid = e.get("logonid") or "-"
        lines.append(f"{e['t']}  {e['case'][-8:]}  e{e['entry']:>4}  "
                     f"{e['host']:8} {e['principal']:16} {e['kind']:8} {lid:12} {e.get('detail','')[:40]}")
    return "\n".join(lines)


def stats() -> dict:
    entries = read_all()
    by_kind = {}
    by_host = {}
    for e in entries:
        by_kind[e.get("kind", "?")] = by_kind.get(e.get("kind", "?"), 0) + 1
        by_host[e.get("host", "?")] = by_host.get(e.get("host", "?"), 0) + 1
    return {
        "total": len(entries),
        "cases": len({e.get("case") for e in entries}),
        "hosts": len(by_host),
        "by_kind": by_kind,
        "by_host": by_host,
    }
