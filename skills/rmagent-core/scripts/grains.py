#!/usr/bin/env python3
"""Grain firewall — one ALLOWED set per rmagent skill.

Template rule: one grain per skill. App ETW names are illegal on so;
identity names are illegal on at; fr asks nothing.
"""
from __future__ import annotations

IDENTITY = frozenset({
    "attest", "sketch", "edges", "explain", "netedges", "pslogs",
    "kernring", "attackmap", "flowstats", "deepwindow", "profile",
    "lineage", "dns", "attackmap2", "canary", "regedges",
})

LINUX_IDENTITY = frozenset({
    "attest", "sketch", "edges", "explain", "attackmap",
})

APP = frozenset({
    "apptrace", "appslow", "apperrors", "appnet", "appproc", "appsysmon", "ringhealth",
})

AGENT = frozenset({
    "agents", "agentstate", "agenttrace", "agentnet",
    "agentmodels", "agentdrift", "agentdeep",
})

ISO = frozenset({
    "txnattest", "txntrace", "txnhops", "txnslow", "txnfail", "txnbaseline",
})

PAY = frozenset({
    "pay_attest", "switch_txn", "core_auth", "pay_sketch", "hop_delta",
})

# Flight Recorder records investigations. It never knocks.
FR = frozenset()

BY_SKILL = {
    "rmagent-so": IDENTITY,
    "rmagent-windows": IDENTITY,  # facade: same grain as so
    "rmagent-linux": LINUX_IDENTITY,
    "rmagent-at": APP,
    "rmagent-ao": AGENT,
    "rmagent-fr": FR,
    "rmagent-iso": ISO,
    "rmagent-pay": PAY,
}

# Names that must not appear on an identity skill (so/windows).
FOREIGN_ON_SO = APP | AGENT | ISO | PAY
# Names that must not appear on the app skill.
FOREIGN_ON_AT = IDENTITY | AGENT | ISO | PAY


def allowed_for(skill_name: str) -> frozenset[str]:
    key = skill_name if skill_name.startswith("rmagent-") else f"rmagent-{skill_name}"
    if key not in BY_SKILL:
        raise KeyError(f"unknown rmagent skill for grain map: {skill_name}")
    return BY_SKILL[key]


def assert_grain(skill_name: str, allowed: set[str] | frozenset[str]) -> None:
    """Raise if *allowed* contains another skill's grain names."""
    want = allowed_for(skill_name)
    extra = set(allowed) - set(want)
    missing_ok = set(want) - set(allowed)  # subsets are legal
    if extra:
        raise ValueError(f"{skill_name} ALLOWED has foreign grain names: {sorted(extra)}")
    _ = missing_ok
