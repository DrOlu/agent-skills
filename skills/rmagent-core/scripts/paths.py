#!/usr/bin/env python3
"""Writable rmagent state — always under ~/.rmagent, never a skill checkout.

A skill tree that grows cases/ or drill JSONL is a lake by accretion.
"""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path.home() / ".rmagent"

CASES = HOME / "cases"
BASELINES = HOME / "baselines"
CENSUS_HISTORY = HOME / "census_history.jsonl"
CENSUS_MISS = HOME / ".census_miss.json"
SILENT = HOME / "silent.json"
ACTUATE_JOURNAL = HOME / "actuate.jsonl"
DRILL = HOME / "drill"
CREDS = HOME / "creds.json"
CONFIG = HOME / "config.json"

HISTORY_MAX = 200  # census jsonl cap — circular trim, not a lake


def ensure() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    CASES.mkdir(parents=True, exist_ok=True)
    BASELINES.mkdir(parents=True, exist_ok=True)
    DRILL.mkdir(parents=True, exist_ok=True)
    try:
        HOME.chmod(0o700)
    except OSError:
        pass
    return HOME


def cases_dir(override: str | None = None) -> Path:
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    env = os.environ.get("RMAGENT_CASES")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    ensure()
    return CASES
