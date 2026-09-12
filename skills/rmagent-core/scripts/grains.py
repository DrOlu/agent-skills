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
    # Rev 21: domain-controller grain. Same identity skill, DC-level events —
    # Kerberos abuse, DCSync, privileged directory changes. A member server
    # answers these with a hole (no DC events); the DC answers them.
    "krb", "dcsync", "dirchange",
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

# Rev 22: the pack grain — one-shot artifact collection + rule-pack logic.
# Collection names are the recipe outputs (prefetch, amcache, usb, shimcache);
# they never overlap the identity or app grains, so a pack can be asked
# alongside so without a name collision. The rule LOGIC lives in
# rmagent-pack/scripts/packs/*.py and is pure (no knock).
PACK = frozenset({
    "prefetch", "amcache", "usb", "shimcache", "packrun",
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
    "rmagent-pack": PACK,
}

# Names that must not appear on an identity skill (so/windows).
FOREIGN_ON_SO = APP | AGENT | ISO | PAY | PACK
# Names that must not appear on the app skill.
FOREIGN_ON_AT = IDENTITY | AGENT | ISO | PAY | PACK


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
