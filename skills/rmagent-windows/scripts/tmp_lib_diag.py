#!/usr/bin/env python3
"""Diagnose the lib.py divergence: which tree holds the true Rev 17/18 lib?

Facts so far:
  - rmagent-so/scripts/lib.py: HAS Rev 17 markers (both on disk and in the
    repo at 38ab437)
  - rmagent-windows/scripts/lib.py: does NOT (disk + repo both old)
  - Yet all the Rev 17 work was edited "in canonical rmagent-windows"...

Hypothesis to check: sync_check.py's CANON is rmagent-windows, but early in
Rev 17 the edits were actually made in rmagent-so's copy (the runtime tree
the tests import), and a later sync --fix pushed OLD windows -> so... except
so clearly HAS the markers now. So the more likely story: the restore-from-
repo just ran and so/windows were restored from the repo; the repo's
windows/lib.py is genuinely old because at PUSH time the live windows/lib.py
was already old (something had reverted it BEFORE the push) — and the push's
check_repo_sync only compares file-by-file, so windows=old-live vs old-repo
looked "in sync" while so carried the real engine.

This script establishes the ground truth: which tree's lib.py does the
RUNNING system actually use, and does ANY copy anywhere have the full
Rev 17/18 engine?"""
import hashlib
import sys
from pathlib import Path

MARKERS = ["_cap_signal", "DEFAULT_TRANSPORT", "mark_silent", "MsgCap",
           "REV 17 (H4)", "silent-host cooldown"]

CANDIDATES = [
    Path.home() / ".agents/skills/rmagent-windows/scripts/lib.py",
    Path.home() / ".agents/skills/rmagent-so/scripts/lib.py",
    Path.home() / ".agents/skills/rmagent-fr/scripts/lib.py",
    Path.home() / ".agents/skills/rmagent-at/scripts/lib.py",
    Path.home() / ".claude/skills/rmagent-windows/scripts/lib.py",
    Path.home() / "work/agent-skills/skills/rmagent-windows/scripts/lib.py",
    Path.home() / "work/agent-skills/skills/rmagent-so/scripts/lib.py",
]

print(f"{'tree':60} {'size':>7}  markers")
best = None
for p in CANDIDATES:
    if not p.exists():
        print(f"{str(p):60} MISSING")
        continue
    t = p.read_text()
    n = sum(1 for m in MARKERS if m in t)
    print(f"{str(p):60} {len(t):>7}  {n}/{len(MARKERS)}")
    if best is None or n > best[1]:
        best = (p, n, len(t), t)

print(f"\nBEST copy: {best[0]} ({best[1]}/{len(MARKERS)} markers, {best[2]} bytes)")
if best[1] < len(MARKERS):
    print("!! NO copy anywhere carries the full Rev 17/18 engine — the git repo is")
    print("   the only recovery source and it may itself be incomplete for lib.py.")
    print("   The test suites will tell us definitively.")
