#!/usr/bin/env python3
"""restore_from_repo — pull the live trees back from the github mirror.

The live ~/.agents/skills trees reverted to their Aug-29 state (cause
unknown — something restored them underneath us; every Rev 17/18 edit is
gone from lib.py, all payloads, correlate, thinker, etc). Commit 38ab437
in ~/work/agent-skills has ALL of it (we verified live==repo before
pushing). This copies REPO -> LIVE for the five skills.

Exception: rmagent-at and sync_check.py survived on disk; the repo copies
are identical to what we pushed, so overwriting them with the repo copy is
lossless either way."""
import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path.home() / "work" / "agent-skills" / "skills"
LIVE = Path.home() / ".agents" / "skills"
SKILLS = ["rmagent-windows", "rmagent-actuate", "rmagent-so", "rmagent-fr", "rmagent-at"]
EXCLUDE_SUFFIX = {".pyc", ".DS_Store"}
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "cases"}


def collect(root: Path) -> dict[str, Path]:
    out = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.suffix in EXCLUDE_SUFFIX or p.name in EXCLUDE_NAMES:
            continue
        if any(part in EXCLUDE_NAMES for part in p.parts):
            continue
        out[str(p.relative_to(root))] = p
    return out


def main() -> int:
    restored = 0
    for name in SKILLS:
        repo = collect(REPO / name)
        live_root = LIVE / name
        live = collect(live_root)
        for rel, src in repo.items():
            dst = live_root / rel
            if rel not in live or not filecmp.cmp(src, dst, shallow=False):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                restored += 1
                print(f"  RESTORE {name}/{rel}")
    print(f"\nrestored {restored} file(s) from commit 38ab437")
    return 0


if __name__ == "__main__":
    sys.exit(main())
