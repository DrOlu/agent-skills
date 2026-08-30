#!/usr/bin/env python3
"""sync_check — fail loudly when the shared engine files drift between the
rmagent skills.

rmagent-windows is the canonical, fully-runnable skill. rmagent-so and
rmagent-fr are separately-loadable views of its halves, kept in sync by copy.
That copy is done by hand (or by a parallel agent session), and it has drifted
before — a change landed in one copy and not the others. This script turns
that silent divergence into a caught error.

Usage:
  python3 sync_check.py            # check all skills against rmagent-windows
  python3 sync_check.py --fix      # copy rmagent-windows -> the others
  python3 sync_check.py --json     # machine-readable

Exit 0 = in sync. Exit 1 = drift (or --fix applied it; re-run to confirm).
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

SKILLS = Path.home() / ".agents" / "skills"
CANON = SKILLS / "rmagent-windows"

# Files that must be byte-identical across the skills that carry them.
# (skill, relative path) — a skill only checks files it actually has.
ENGINE_SO = [
    "scripts/lib.py", "scripts/notify.py", "scripts/hunt.py",
    "scripts/correlate.py", "scripts/drift.py", "scripts/case.py",
    "scripts/thinker.py", "scripts/dthinker.py", "scripts/hop_index.py",
    "scripts/stc.py", "scripts/traj.py", "scripts/causal.py",
    "scripts/otel_emit.py",
]
ENGINE_FR = [
    "scripts/lib.py", "scripts/notify.py", "scripts/stc.py",
    "scripts/traj.py", "scripts/hop_index.py", "scripts/causal.py",
    "scripts/dthinker.py", "scripts/thinker.py", "scripts/otel_emit.py",
    "scripts/census.py",
]
QUESTION_PAYLOADS = [
    "attest", "sketch", "edges", "explain", "netedges", "pslogs",
    "kernring", "attackmap", "attackmap2", "flowstats", "deepwindow",
    "profile", "lineage", "dns",
]


def _build_shared() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for rel in ENGINE_SO:
        out.append(("rmagent-so", rel))
    for rel in ENGINE_FR:
        out.append(("rmagent-fr", rel))
    for q in QUESTION_PAYLOADS:
        out.append(("rmagent-so", f"scripts/questions/windows/{q}.ps1"))
        out.append(("rmagent-fr", f"scripts/questions/windows/{q}.ps1"))
    return out


SHARED = _build_shared()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description="rmagent skill sync check")
    ap.add_argument("--fix", action="store_true",
                    help="copy the canonical file over the drifted one")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    drift: list[dict] = []
    checked = 0
    missing_canon: list[str] = []

    for skill, rel in SHARED:
        canon_p = CANON / rel
        other_p = SKILLS / skill / rel
        if not canon_p.exists():
            missing_canon.append(rel)
            continue
        if not other_p.exists():
            # the skill doesn't carry this file — only a problem if it should
            drift.append({"skill": skill, "file": rel, "issue": "missing_in_skill"})
            continue
        checked += 1
        if sha(canon_p) != sha(other_p):
            drift.append({"skill": skill, "file": rel, "issue": "differs",
                          "canon": sha(canon_p), "skill_hash": sha(other_p)})
            if args.fix:
                other_p.parent.mkdir(parents=True, exist_ok=True)
                other_p.write_bytes(canon_p.read_bytes())
                print(f"  FIXED  {skill}/{rel}")

    if missing_canon:
        # dedupe for the report
        for rel in sorted(set(missing_canon)):
            print(f"  WARN   canonical rmagent-windows is missing {rel}")

    if args.json:
        print(json.dumps({"checked": checked, "drift": drift,
                          "missing_canonical": sorted(set(missing_canon))}, indent=2))
    else:
        print(f"checked {checked} shared files across rmagent-so and rmagent-fr")
        if not drift:
            print("IN SYNC — all shared files byte-identical to rmagent-windows")
        else:
            print(f"DRIFT: {len(drift)} file(s) differ from the canonical skill:")
            for d in drift:
                print(f"  {d['skill']:14} {d['file']:48} {d['issue']}")

    return 0 if not drift else 1


if __name__ == "__main__":
    sys.exit(main())