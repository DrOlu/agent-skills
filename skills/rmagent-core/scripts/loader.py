#!/usr/bin/env python3
"""Load the canonical rmagent engine without sys.path + import lib.

`import lib` after sys.path.insert re-imports THIS skill's lib.py (circular).
Load rmagent-core/scripts/engine.py under a private module name, then bind
ALLOWED + QDIR to the calling skill's grain and payload tree.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent
_SKILLS = _HERE.parents[1]  # ~/.agents/skills


def _engine_candidates() -> list[Path]:
    home = Path.home()
    return [
        _HERE / "engine.py",
        _SKILLS / "rmagent-core" / "scripts" / "engine.py",
        home / ".agents" / "skills" / "rmagent-core" / "scripts" / "engine.py",
        home / "work" / "agent-skills" / "skills" / "rmagent-core" / "scripts" / "engine.py",
        # last-resort: old so copy, only if core engine is missing
        _SKILLS / "rmagent-so" / "scripts" / "lib.py",
    ]


def load_engine(name: str = "_rmagent_shared_lib") -> ModuleType:
    for f in _engine_candidates():
        if f.exists():
            spec = importlib.util.spec_from_file_location(name, f)
            if spec is None or spec.loader is None:
                continue
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("shared rmagent engine (rmagent-core/scripts/engine.py) not found")


def load_grains():
    g = _HERE / "grains.py"
    spec = importlib.util.spec_from_file_location("_rmagent_grains", g)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def apply_grain(engine: ModuleType, skill_name: str) -> ModuleType:
    """Replace engine.ALLOWED / PHASE0_SKILLS with the grain map."""
    grains = load_grains()
    allowed = set(grains.allowed_for(skill_name))
    engine.ALLOWED = allowed
    if hasattr(engine, "PHASE0_SKILLS"):
        engine.PHASE0_SKILLS = allowed
    return engine


def bind(engine: ModuleType, skill_name: str, skill_dir: Path) -> ModuleType:
    """Grain firewall + payload directory for one skill tree."""
    apply_grain(engine, skill_name)
    skill_dir = Path(skill_dir)
    engine.SKILL_DIR = skill_dir
    engine.QDIR = skill_dir / "scripts" / "questions"
    return engine


def load_skill(skill_name: str, skill_dir: Path, name: str = "_rmagent_shared_lib") -> ModuleType:
    return bind(load_engine(name), skill_name, skill_dir)
