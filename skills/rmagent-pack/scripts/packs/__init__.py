#!/usr/bin/env python3
"""packs — the registry. Import a pack here to make it usable by the CLI."""
from __future__ import annotations

from kerberos_ad import KERBEROS_AD
from artifact_recipes import ARTIFACT_RECIPES

ALL_PACKS = {
    "kerberos_ad": KERBEROS_AD,
    "artifact_recipes": ARTIFACT_RECIPES,
}


def get(name: str):
    if name not in ALL_PACKS:
        raise KeyError(f"unknown pack '{name}'. known: {sorted(ALL_PACKS)}")
    return ALL_PACKS[name]
