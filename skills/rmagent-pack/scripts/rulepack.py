#!/usr/bin/env python3
"""rulepack — the recipe/rule logic, as CODE, not prose.

A pack is a named collection of RULES. A rule is:
  events      which event IDs / sources it looks at
  filters     which rows it keeps (field predicates)
  thresholds  when it FIRES (counts, windows, distincts, ratios)
  severity    what it means if it fires

This module is pure: give it rows, it returns findings. No I/O, no network.
Every pack ships its own tests. The packs are a SOURCE OF DETECTION IDEAS
(facts from Velociraptor's rule packs / Sigma / ATT&CK), converted into
rmagent-shaped questions and payloads — never a server, never a lake.

Ethos carried into the logic:
  - a rule that fired on a BLIND source is not a finding, it is a hole
  - thresholds have a minimum sample (n>=30) before a baseline ratio is trusted
  - a rule returns COUNTS and a short example list, never the row lake
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Rule:
    id: str
    title: str
    events: list[int]                 # e.g. [4769]
    source: str                       # "kernel-legal-20" | "dns" | "symon" | "prefetch" ...
    filters: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"
    why: str = ""
    technique: str = ""               # ATT&CK id, for the report

    def matches(self, row: dict) -> bool:
        """Field predicates. eq / ne / in / notin / gt / lt / contains / regex."""
        for key, spec in self.filters.items():
            if not _one(row, key, spec):
                return False
        return True


def _val(row: dict, key: str):
    # dotted paths: "event.data.SubjectUserName"
    cur = row
    for part in key.split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
                continue
            # case-insensitive fallback (Windows event data varies)
            lk = {k.lower(): k for k in cur.keys()}
            if part.lower() in lk:
                cur = cur[lk[part.lower()]]
                continue
            return None
        return None
    return cur


def _one(row: dict, key: str, spec) -> bool:
    v = _val(row, key)
    if not isinstance(spec, dict):
        return str(v).lower() == str(spec).lower()
    for op, want in spec.items():
        sv = "" if v is None else str(v)
        if op == "eq" and sv.lower() != str(want).lower():
            return False
        if op == "ne" and sv.lower() == str(want).lower():
            return False
        if op == "in" and sv.lower() not in [str(x).lower() for x in want]:
            return False
        if op == "notin" and sv.lower() in [str(x).lower() for x in want]:
            return False
        if op == "contains" and str(want).lower() not in sv.lower():
            return False
        if op == "gt":
            try:
                if not (float(sv) > float(want)):
                    return False
            except ValueError:
                return False
        if op == "lt":
            try:
                if not (float(sv) < float(want)):
                    return False
            except ValueError:
                return False
        if op == "regex":
            import re
            if not re.search(str(want), sv, re.I):
                return False
    return True


def apply_rule(rule: Rule, rows: list[dict], blind: bool = False) -> dict:
    """Run ONE rule over rows. Returns a finding-shaped dict.

    If the source is BLIND, the rule cannot fire: it returns a hole. That is
    the standing rule — an empty/untested source is not a clean result.
    """
    hits = [r for r in rows if r.get("eid") in rule.events or r.get("id") in rule.events]
    hits = [r for r in hits if rule.matches(r)]

    if blind:
        return {"rule": rule.id, "fired": False, "hole": True,
                "why": "source blind — a rule that fired here would be an artifact of blindness",
                "severity": rule.severity}

    t = rule.thresholds or {}
    fired = False
    detail: dict[str, Any] = {"matched": len(hits)}

    if "count" in t:
        fired = fired or len(hits) >= int(t["count"])
    if "distinct" in t:
        field = t["distinct"]
        distinct = {str(_val(h, field)) for h in hits}
        detail["distinct"] = len(distinct)
        # fire when the distinct-value count is met (a sweep is many distinct
        # SPNs, not one repeated request)
        need = int(t.get("count", 1))
        if len(distinct) >= need:
            fired = True
    if "ratio" in t:
        # e.g. failed/success ratio — needs a denominator set
        denom_field = t.get("denominator", "success")
        denom = t.get("denominator_n") or 0
        if denom >= int(t.get("min_n", 30)):
            detail["ratio"] = len(hits) / denom if denom else None
            fired = fired or (detail["ratio"] or 0) >= float(t["ratio"])
        else:
            detail["ratio"] = None
            detail["ratio_hole"] = f"denominator n={denom} < 30 — ratio not trusted"
    if "any" in t and t["any"]:
        fired = fired or len(hits) >= 1
    if "never_seen_before" in t and t["never_seen_before"]:
        fired = fired or len(hits) >= 1

    return {
        "rule": rule.id,
        "title": rule.title,
        "fired": fired,
        "severity": rule.severity if fired else "info",
        "technique": rule.technique,
        "why": rule.why,
        "count": len(hits),
        "examples": [_slim(h) for h in hits[:3]],   # never the lake
        "detail": detail,
    }


def _slim(row: dict) -> dict:
    """A 3-field example row — enough to act on, not a dump."""
    keep = ("t", "eid", "user", "spn", "src", "dest", "process", "path")
    return {k: row[k] for k in keep if k in row}


@dataclass
class Pack:
    id: str
    title: str
    description: str
    rules: list[Rule]
    source_kind: str = "windows-eventlog"   # how the payload collects

    def run(self, rows_by_eid: list[dict], blind_sources: set[str] | None = None) -> dict:
        blind_sources = blind_sources or set()
        findings = []
        for r in self.rules:
            blind = r.source in blind_sources
            findings.append(apply_rule(r, rows_by_eid, blind=blind))
        fired = [f for f in findings if f["fired"]]
        return {
            "pack": self.id,
            "title": self.title,
            "n_rules": len(self.rules),
            "n_fired": len(fired),
            "findings": findings,
        }
