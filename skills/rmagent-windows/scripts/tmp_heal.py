#!/usr/bin/env python3
"""heal.py — restore the trees to Rev 17/18 state after the unknown reversion.

SOURCES OF TRUTH (verified during diagnosis):
  - rmagent-so/scripts/lib.py (26089 bytes, 6/6 markers) = the full Rev 17/18
    engine. windows/fr/at libs are supposed to be byte-identical to it.
  - github 38ab437 payloads (attest/edges/etc with REV 17/18 markers) for the
    question payloads + sync_check.py + thinker.py + hop_index.py + otel_emit.py
  - actuate: journal.py survived in the repo (check), actuate.py must be
    rewritten from the conversation (test_actuate.py at 38ab437 is its
    executable spec).

Steps:
  1. so/lib.py -> windows/lib.py, fr/lib.py, at/lib.py (the shared engine)
  2. so payload/thinker/hop_index/otel_emit/case/correlate/hunt/drift ->
     windows (sync_check's CANON tree must carry the Rev 17/18 versions)
  3. run sync_check --fix to push windows -> so/fr/at everywhere else
  4. verify markers + run the full regression
"""
import filecmp
import shutil
from pathlib import Path

AG = Path.home() / ".agents/skills"
SO = AG / "rmagent-so/scripts"
WIN = AG / "rmagent-windows/scripts"
FR = AG / "rmagent-fr/scripts"
AT = AG / "rmagent-at/scripts"

# files that must be byte-identical across so/fr/at (per sync_check) and are
# held CORRECTLY in the so tree right now
SHARED_FROM_SO = [
    "lib.py", "notify.py", "stc.py", "traj.py", "hop_index.py",
    "otel_emit.py", "thinker.py", "dthinker.py", "causal.py",
    "correlate.py", "drift.py", "case.py", "hunt.py",
    "test_enterprise.py", "test_budget.py", "test_stc_v2.py",
    "test_failed_sources.py",
]
# the canonical windows tree also carries the QUESTION payloads; the so tree
# has the identical synced copies
PAYLOADS = [
    "attest", "sketch", "edges", "explain", "netedges", "pslogs", "kernring",
    "attackmap", "attackmap2", "flowstats", "deepwindow", "profile",
    "lineage", "dns", "canary",
    "apptrace", "appslow", "apperrors", "appnet", "appproc", "appsysmon",
]

n = 0

# 1. the engine to windows/fr/at
for rel in SHARED_FROM_SO:
    src = SO / rel
    if not src.exists():
        print(f"  skip (missing in so): {rel}")
        continue
    for dst in (WIN / rel, FR / rel, AT / rel):
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(src, dst)
            globals()["n"] = n = n + 1
            print(f"  SO -> {dst.relative_to(AG)}")

# 2. payloads so -> windows (windows is sync_check's CANON for payloads)
for name in PAYLOADS:
    src = SO / "questions/windows" / f"{name}.ps1"
    dst = WIN / "questions/windows" / f"{name}.ps1"
    if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
        print(f"  SO -> windows/questions/windows/{name}.ps1")

print(f"\nhealed {n} files")
