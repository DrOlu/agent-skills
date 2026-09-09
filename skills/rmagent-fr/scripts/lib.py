#!/usr/bin/env python3
"""rmagent-fr grain wrapper. Engine in rmagent-core.

Flight Recorder records cases. ALLOWED is empty — it never knocks a box.
ask() refuses actuate and every question name. Cap 32 KB. A hole is an answer.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
_SKILL = "rmagent-fr"


def _loader_path() -> Path:
    for p in (
        SKILL_DIR.parent / "rmagent-core" / "scripts" / "loader.py",
        Path.home() / ".agents" / "skills" / "rmagent-core" / "scripts" / "loader.py",
        Path.home() / "work" / "agent-skills" / "skills" / "rmagent-core" / "scripts" / "loader.py",
    ):
        if p.exists():
            return p
    raise ImportError("rmagent-core/scripts/loader.py not found")


def _load():
    p = _loader_path()
    spec = importlib.util.spec_from_file_location("_rmagent_loader", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.load_skill(_SKILL, SKILL_DIR)


_eng = _load()
ALLOWED = _eng.ALLOWED  # empty — fr does not knock
PHASE0_SKILLS = ALLOWED
MAX_PULL_BYTES = _eng.MAX_PULL_BYTES
QDIR = _eng.QDIR
ask = _eng.ask
hole = _eng.hole


def __getattr__(name):
    return getattr(_eng, name)
