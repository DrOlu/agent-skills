#!/usr/bin/env python3
"""rmagent-pack lib — same engine (rmagent-core) + the pack grain.

  ask(row, "prefetch")            -> one-shot collection, capped, holes
  run_pack("kerberos_ad", rows)   -> rule logic over already-pulled rows

The rule logic and the collection are deliberately separate:
  collection answers "give me what's on the box" (one question)
  a pack answers "what does it mean" (pure, testable, no I/O)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
_HERE = Path(__file__).resolve().parent


def _loader():
    for p in (
        SKILL_DIR.parent / "rmagent-core" / "scripts" / "loader.py",
        Path.home() / ".agents" / "skills" / "rmagent-core" / "scripts" / "loader.py",
    ):
        if p.exists():
            spec = importlib.util.spec_from_file_location("_rmagent_loader_pack", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("rmagent-core/scripts/loader.py not found")


_eng = _loader().load_skill("rmagent-pack", SKILL_DIR)
ALLOWED = _eng.ALLOWED
PHASE0_SKILLS = ALLOWED
MAX_PULL_BYTES = _eng.MAX_PULL_BYTES
QDIR = _eng.QDIR
ask = _eng.ask
hole = _eng.hole


def __getattr__(name):
    return getattr(_eng, name)


def run_pack(pack_name: str, rows: list[dict], blind_sources: set[str] | None = None) -> dict:
    """Run a pack's rule logic over rows already collected. Pure, no I/O."""
    sys.path.insert(0, str(_HERE))
    sys.path.insert(0, str(_HERE / "packs"))
    import packs as _packs  # type: ignore
    return _packs.get(pack_name).run(rows, blind_sources=blind_sources)


def list_packs() -> list[str]:
    sys.path.insert(0, str(_HERE))
    sys.path.insert(0, str(_HERE / "packs"))
    import packs as _packs  # type: ignore
    return sorted(_packs.ALL_PACKS)
