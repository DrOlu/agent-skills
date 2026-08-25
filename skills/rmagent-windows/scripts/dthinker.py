#!/usr/bin/env python3
"""Distributed thinker — correlation ACROSS hosts using the hop index.

The per-witness thinker (thinker.py) reasons about one box's metrics over time.
This module reasons about the ESTATE: joins findings across hosts and cases to
spot the pattern no single question reveals.

  "failed logons on WS1 at 14:02, a new admin on WS2 at 14:04, an outbound
   connection from WS1 at 14:05 — three findings, one window, one story."

Correlations detected:
  temporal_cluster    — multiple distinct hop kinds within a short window
  cross_host_chain    — the same principal hopping hosts in sequence
  repeat_offender     — a principal/host pair seen in multiple different cases
  session_correlation — same account + same source IP on multiple hosts (the REAL join)

NOTE: LogonIds (LUIDs) are only unique WITHIN a host. Two hosts showing the same
LogonId is coincidence, not correlation. The real cross-host join is account +
source IP + timestamp window.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from collections import defaultdict

# Window for "these events are one story"
CLUSTER_WINDOW_S = 300        # 5 minutes
CHAIN_WINDOW_S = 3600         # 1 hour for host-to-host chains


def think_distributed(index_entries: list[dict]) -> list[dict]:
    """Reason over hop-index entries across hosts and cases."""
    if len(index_entries) < 2:
        return []
    findings: list[dict] = []
    parsed = _parse(index_entries)

    findings += _temporal_cluster(parsed)
    findings += _cross_host_chain(parsed)
    findings += _repeat_offender(parsed)
    findings += _session_correlation(parsed)

    return findings


def _parse(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        try:
            t = datetime.fromisoformat(str(e.get("t", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        out.append({**e, "_ts": t})
    return sorted(out, key=lambda x: x["_ts"])


# ---------------------------------------------------------------- correlations
def _temporal_cluster(parsed: list[dict]) -> list[dict]:
    """Multiple distinct hop kinds within CLUSTER_WINDOW_S — one story."""
    findings = []
    window = timedelta(seconds=CLUSTER_WINDOW_S)
    i = 0
    while i < len(parsed):
        j = i
        group = []
        while j < len(parsed) and (parsed[j]["_ts"] - parsed[i]["_ts"]) <= window:
            group.append(parsed[j])
            j += 1
        if len(group) >= 3:
            kinds = {g.get("kind") for g in group}
            hosts = {g.get("host") for g in group}
            if len(kinds) >= 3:
                findings.append({
                    "kind": "temporal_cluster",
                    "witness": "+".join(sorted(str(h) for h in hosts)),
                    "what": f"{len(group)} hops of {len(kinds)} different kinds "
                            f"({', '.join(sorted(kinds))}) across {len(hosts)} host(s) "
                            f"within {CLUSTER_WINDOW_S}s — one story, not coincidence",
                    "severity": "critical",
                    "window": [group[0]["t"], group[-1]["t"]],
                })
        i = j if j > i else i + 1
    return findings


def _cross_host_chain(parsed: list[dict]) -> list[dict]:
    """The same principal hopping hosts in sequence — the lateral movement walk."""
    findings = []
    by_principal = defaultdict(list)
    for p in parsed:
        by_principal[p.get("principal", "?")].append(p)
    for principal, hops in by_principal.items():
        hops = sorted(hops, key=lambda x: x["_ts"])
        chain = []
        for h in hops:
            if not chain or h["host"] != chain[-1]["host"]:
                chain.append(h)
            else:
                chain[-1] = h
        hosts_seq = [c["host"] for c in chain]
        if len(set(hosts_seq)) >= 2:
            # check the hops are within CHAIN_WINDOW_S of each other
            if (chain[-1]["_ts"] - chain[0]["_ts"]).total_seconds() <= CHAIN_WINDOW_S:
                findings.append({
                    "kind": "cross_host_chain",
                    "witness": " → ".join(hosts_seq),
                    "what": f"principal '{principal}' walked {len(set(hosts_seq))} hosts "
                            f"in sequence: {' → '.join(hosts_seq)} within "
                            f"{CHAIN_WINDOW_S}s — lateral movement",
                    "severity": "high",
                })
    return findings


def _repeat_offender(parsed: list[dict]) -> list[dict]:
    """A principal/host pair seen in multiple DIFFERENT cases — recurring activity."""
    findings = []
    pair_cases = defaultdict(set)
    for p in parsed:
        pair_cases[(p.get("principal"), p.get("host"))].add(p.get("case"))
    for (principal, host), cases in pair_cases.items():
        if len(cases) >= 3:
            findings.append({
                "kind": "repeat_offender",
                "witness": str(host),
                "what": f"principal '{principal}' on {host} appears in {len(cases)} "
                        f"distinct cases — recurring activity worth investigating",
                "severity": "medium",
            })
    return findings


def _session_correlation(parsed: list[dict]) -> list[dict]:
    """Same account + same source IP on multiple hosts — the REAL cross-host join.

    LogonIds are per-host only, so they cannot join across boxes. What CAN join:
    the same account authenticating from the same source IP to multiple hosts
    within a short window. That is one actor moving laterally, and it is the
    strongest cross-host correlation available from event data alone.
    """
    findings = []
    sessions = defaultdict(lambda: {"hosts": set(), "ts": []})
    for p in parsed:
        acct = p.get("principal")
        src = p.get("src_ip") or ""
        host = p.get("host")
        # FP guard: without a real source IP there is no join — (account, "")
        # would match across hosts and flag any same-account activity as
        # lateral movement. Skip entries with no source.
        if acct and host and src:
            key = (str(acct).lower(), str(src))
            sessions[key]["hosts"].add(host)
            sessions[key]["ts"].append(p.get("_ts"))
    for (acct, src), info in sessions.items():
        if len(info["hosts"]) >= 2:
            ts_sorted = sorted(t for t in info["ts"] if t)
            span_s = (ts_sorted[-1] - ts_sorted[0]).total_seconds() if len(ts_sorted) >= 2 else 0
            if span_s <= CHAIN_WINDOW_S:
                hosts = sorted(str(h) for h in info["hosts"])
                findings.append({
                    "kind": "session_correlation",
                    "witness": "+".join(hosts),
                    "what": f"account '{acct}' from source '{src or '?'}' authenticated to "
                            f"{len(hosts)} hosts ({', '.join(hosts)}) within {span_s:.0f}s — "
                            f"one actor moving laterally",
                    "severity": "critical",
                })
    return findings


def render(findings: list[dict]) -> str:
    if not findings:
        return "(no cross-host correlations)"
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    lines = []
    for f in sorted(findings, key=lambda x: sev_order.get(x.get("severity", "low"), 3)):
        sev = f.get("severity", "low").upper()
        lines.append(f"[{sev:8}] {f['kind']:18} {f.get('witness', '?'):24} {f['what']}")
    return "\n".join(lines)
