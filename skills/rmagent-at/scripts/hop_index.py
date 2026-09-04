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
INDEX_MAX = 5000  # keep the last 5000 hops
# REV 18 (M4): age-based retention, not just line-count. On a busy estate
# 5000 lines is a day; the "months of cases" claim was aspirational. Entries
# older than KEEP_DAYS are shed at the next trim. And because a trimmed index
# silently answering False to seen_before() was a false negative factory,
# queries can distinguish "never seen" from "beyond retention".
KEEP_DAYS = 30
_oldest_entry_ts: dict = {"t": None}

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
    ts = t or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    e = {
        "t": ts,
        "case": case,
        "entry": entry_id,
        "host": host,
        "principal": principal,
        "kind": hop_kind,
    }
    # rev 14: hour_of_day for the per-account behavioural baseline —
    # "this account has never logged in at 3am before" without a lake.
    try:
        hour = int(ts[11:13])
        e["hour"] = hour
    except (ValueError, IndexError):
        pass
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
    """Line-count AND age trim (REV 18 M4). O(n) per call is fine at 5000
    lines but only when needed: skip when both budgets are comfortably clear."""
    try:
        if not INDEX.exists():
            return
        lines = INDEX.read_text().splitlines()
        if len(lines) <= INDEX_MAX:
            # age check is still cheap and keeps the retention promise
            cutoff = time.time() - KEEP_DAYS * 86400
            old = 0
            for l in lines[:50]:
                try:
                    ts = json.loads(l).get("t")
                    from datetime import datetime
                    if datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() < cutoff:
                        old += 1
                except Exception:
                    old += 1
            if old == 0:
                return
        cutoff = time.time() - KEEP_DAYS * 86400
        kept = []
        from datetime import datetime
        for l in lines:
            try:
                ts = json.loads(l).get("t")
                ok = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() >= cutoff
            except Exception:
                ok = True  # unparseable lines are kept (never destroy on a parse error)
            if ok:
                kept.append(l)
        kept = kept[-INDEX_MAX:]
        if len(kept) < len(lines):
            INDEX.write_text("\n".join(kept) + "\n")
    except OSError:
        pass


def retention_horizon() -> str | None:
    """The timestamp of the oldest entry the index still holds, or None when
    empty. seen_before() uses it to answer 'beyond retention' honestly."""
    try:
        if not INDEX.exists():
            return None
        lines = INDEX.read_text().splitlines()
        for l in lines:
            try:
                return json.loads(l).get("t")
            except Exception:
                continue
    except OSError:
        pass
    return None


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


def seen_before(host: str, principal: str, within_hours: float = 168):
    """Has this principal been seen on this host recently (default: 7 days)?

    REV 18 (M4): returns (seen: bool, honest: bool). honest=False means the
    answer extends beyond the index's retention horizon — 'False' then means
    'no record within what I can see', NOT 'never happened'. Callers that
    need the old bool can use `seen_before(...)[0]`."""
    cutoff = time.time() - (within_hours * 3600)
    for e in by_principal(principal):
        if e.get("host") == host:
            try:
                from datetime import datetime, timezone
                et = datetime.fromisoformat(e["t"].replace("Z", "+00:00")).timestamp()
                if et >= cutoff:
                    return True, True
            except (ValueError, KeyError):
                continue
    # not found — is that an honest answer or a retention boundary?
    horizon = retention_horizon()
    try:
        from datetime import datetime
        h_ts = datetime.fromisoformat(horizon.replace("Z", "+00:00")).timestamp() if horizon else None
    except (ValueError, TypeError):
        h_ts = None
    honest = bool(h_ts and h_ts <= cutoff)
    return False, honest


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
