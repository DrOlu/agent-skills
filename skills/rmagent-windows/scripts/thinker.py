#!/usr/bin/env python3
"""Thinker for RMAgent — persistent reasoning between knocks.

Stolen from Headlong's insight (github.com/laude-institute/headlong): the
observatory's biggest gap is that it only sees what it asks about. A thinker
that sits between census runs and REASONS about what it saw — "admin_fail went
from 0 to 1 to 3 in three minutes; that's acceleration, not noise" — catches
patterns that no single question reveals.

This is NOT the full Headlong runtime (no LLM loop, no persistent mind, no
$1-2/hour thinking). It is a deterministic pattern-recognition pass over the
last N census results, run between knocks. It looks for:

  acceleration   — a metric that is rising across consecutive censuses
  cliff          — a metric that jumped suddenly between two censuses
  persistence    — a condition that has held for N consecutive censuses
  correlation    — two witnesses showing the same pattern at the same time
  silence        — a witness that stopped answering (the hole that is an answer)

Each finding is written to the case trajectory as a THOUGHT entry. The thought
is the agent's reasoning; the trajectory records it so a human can walk back
to the exact observation that triggered it.

Usage (from hunt.py or the watchdog):
    from thinker import think
    findings = think(census_history)   # list of dicts from census.py runs
    for f in findings:
        traj.think(f["what"])
"""
from __future__ import annotations
from typing import Any

# Metrics from census attest that are worth reasoning about.
# (key, direction, human name, threshold for "concerning")
METRICS = [
    ("admin_failed_60s", "up", "failed admin logons (60s)", 3),
    ("admin_ok_5min", "up", "successful admin logons (5min)", 10),
    ("local_admin_count", "up", "local admin count", 0),      # any change is notable
    ("system_remote_conns", "up", "SYSTEM remote connections", 5),
]

# Conditions that, if they persist across censuses, are a finding.
PERSISTENT = [
    ("admin_failed_60s", ">", 0, "failed admin logons continuing"),
    ("sysmon_status", "not_running", "Running", "Sysmon not running"),
]


def think(history: list[dict]) -> list[dict]:
    """Reason over a sequence of census history entries. Returns findings.

    history: list of {t, witness, metric...} entries from census_history.jsonl,
             oldest first. Each entry is ONE witness's result from ONE census.
             A witness that was silent has {"t":..., "witness":..., "silent": true}.
    """
    if len(history) < 2:
        return []
    findings: list[dict] = []

    # Group entries by census timestamp, then by witness
    # → [{ws1: {...}, ws2: {...}}, {ws1: {...}, ws2: {...}}, ...]
    by_time: dict[str, dict] = {}
    for e in history:
        t = e.get("t", "?")
        by_time.setdefault(t, {})[e.get("witness", "?")] = {
            k: v for k, v in e.items() if k not in ("t", "witness")
        }
    censuses = [by_time[t] for t in sorted(by_time.keys())]

    witnesses = set()
    for c in censuses:
        witnesses.update(c.keys())

    for w in sorted(witnesses):
        series = [c.get(w) for c in censuses]
        present = [s for s in series if s and not s.get("silent")]

        # --- silence: the box stopped answering ---
        if len(present) < len(series):
            absent = 0
            for s in reversed(series):
                if not s or s.get("silent"):
                    absent += 1
                else:
                    break
            if absent >= 2:
                findings.append({
                    "kind": "silence",
                    "witness": w,
                    "what": f"{w} has been silent for {absent} consecutive censuses — "
                            f"sensor failure or stripped witness, not 'nothing happened'",
                    "severity": "critical",
                })

        if len(present) < 2:
            continue

        # --- per-metric reasoning ---
        for key, direction, name, threshold in METRICS:
            vals = [s.get(key) for s in present if s.get(key) is not None]
            if len(vals) < 2:
                continue

            # acceleration: rising across 3+ consecutive censuses
            if len(vals) >= 3 and all(isinstance(vals[i], (int, float)) and
                                      isinstance(vals[i + 1], (int, float)) and
                                      vals[i] < vals[i + 1]
                                      for i in range(len(vals) - 1)):
                findings.append({
                    "kind": "acceleration",
                    "witness": w,
                    "metric": key,
                    "values": vals,
                    "what": f"{name} on {w} is accelerating: {vals} over {len(vals)} censuses — "
                            f"pattern, not noise",
                    "severity": "high" if vals[-1] >= threshold else "medium",
                })

            # cliff: sudden jump between two consecutive censuses
            elif len(vals) >= 2:
                last, prev = vals[-1], vals[-2]
                if isinstance(last, (int, float)) and isinstance(prev, (int, float)):
                    if prev == 0 and last >= max(3, threshold):
                        findings.append({
                            "kind": "cliff",
                            "witness": w,
                            "metric": key,
                            "values": [prev, last],
                            "what": f"{name} on {w} jumped from {prev} to {last} between censuses — "
                                    f"sudden onset",
                            "severity": "high",
                        })
                    elif prev > 0 and last >= prev * 3 and last >= threshold:
                        findings.append({
                            "kind": "cliff",
                            "witness": w,
                            "metric": key,
                            "values": [prev, last],
                            "what": f"{name} on {w} tripled from {prev} to {last} between censuses",
                            "severity": "medium",
                        })

        # --- persistent conditions ---
        for key, op, val, desc in PERSISTENT:
            vals = [s.get(key) for s in present if s.get(key) is not None]
            if len(vals) < 3:
                continue
            if op == ">" and all(isinstance(v, (int, float)) and v > val for v in vals[-3:]):
                findings.append({
                    "kind": "persistence",
                    "witness": w,
                    "metric": key,
                    "values": vals[-3:],
                    "what": f"{desc} on {w} for {len(vals[-3:])} consecutive censuses "
                            f"(values: {vals[-3:]})",
                    "severity": "high",
                })
            elif op == "not_running" and all(
                    isinstance(v, str) and "Running" not in v for v in vals[-3:]):
                findings.append({
                    "kind": "persistence",
                    "witness": w,
                    "metric": key,
                    "values": vals[-3:],
                    "what": f"{desc} on {w} (status: {vals[-1]}) — the primary ring is down",
                    "severity": "high",
                })

    # --- correlation: two witnesses showing the same pattern ---
    if len(witnesses) >= 2:
        for key, direction, name, threshold in METRICS:
            rising = []
            for w in sorted(witnesses):
                series = [c.get(w) for c in censuses if c.get(w)]
                vals = [s.get(key) for s in series if s.get(key) is not None]
                if (len(vals) >= 2 and isinstance(vals[-1], (int, float))
                        and isinstance(vals[-2], (int, float))
                        and vals[-1] > vals[-2] and vals[-1] >= threshold):
                    rising.append(w)
            if len(rising) >= 2:
                findings.append({
                    "kind": "correlation",
                    "witness": "+".join(rising),
                    "metric": key,
                    "what": f"{name} rising on {len(rising)} witnesses simultaneously "
                            f"({', '.join(rising)}) — coordinated activity, not coincidence",
                    "severity": "critical",
                })

    return findings


def render(findings: list[dict]) -> str:
    """Human-readable rendering of thinker findings."""
    if not findings:
        return "(no patterns detected)"
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    lines = []
    for f in sorted(findings, key=lambda x: sev_order.get(x.get("severity", "low"), 3)):
        sev = f.get("severity", "low").upper()
        lines.append(f"[{sev:8}] {f['kind']:12} {f.get('witness', '?'):8} {f['what']}")
    return "\n".join(lines)
