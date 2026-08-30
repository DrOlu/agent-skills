#!/usr/bin/env python3
"""check_drift — the committed, runnable form of the drift checks.

The pre-commit hook in .git/hooks/pre-commit is NOT version-controlled (git
never tracks its own hooks), so its logic lives here where it can be reviewed,
run on demand, and survive a fresh clone. The hook and this file do the same
job; keep them in step if you change one.

TWO KINDS OF DRIFT, BOTH OF WHICH HAVE HAPPENED
-----------------------------------------------
1. ENGINE DRIFT between skills. The shared engine files (lib.py, correlate.py,
   attest.ps1, ...) must be byte-identical across rmagent-windows / -so / -fr.
   This drifted silently for a full day: rev 15 was built in rmagent-so while
   rmagent-windows (canonical) and rmagent-fr kept the pre-rev-15 files.
   sync_check.py detects it; this script re-uses its file list.

2. LIVE-REPO DRIFT. The live skills in ~/.agents/skills are the source of truth
   — they are what actually runs. The repo sat at rev 11 while live was at rev
   15 and nothing noticed, because nothing compared them.
   check_repo_sync.py detects it across all 8 skills.

Usage:
  python3 check_drift.py            # run both checks, exit 1 on any drift
  python3 check_drift.py --json
  python3 check_drift.py --fix      # engine only: copy windows -> so/fr

Exit 0 = in sync. Exit 1 = drift (or --fix applied it; re-run to confirm).
Bypass the pre-commit hook with: git commit --no-verify   (know what you are doing)
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent  # skills/ directory

# the shared engine files, mirroring sync_check.py's list
ENGINE_SO = ["lib.py", "notify.py", "hunt.py", "correlate.py", "drift.py",
             "case.py", "thinker.py", "dthinker.py", "hop_index.py",
             "stc.py", "traj.py", "causal.py", "otel_emit.py"]
ENGINE_FR = ["lib.py", "notify.py", "stc.py", "traj.py", "hop_index.py",
             "causal.py", "dthinker.py", "thinker.py", "otel_emit.py", "census.py"]
QUESTIONS = ["attest", "sketch", "edges", "explain", "netedges", "pslogs",
             "kernring", "attackmap", "attackmap2", "flowstats", "deepwindow",
             "profile", "lineage", "dns"]


def engine_pairs() -> list[tuple[str, str]]:
    out = []
    for f in ENGINE_SO:
        out.append(("rmagent-so", f"scripts/{f}"))
    for f in ENGINE_FR:
        out.append(("rmagent-fr", f"scripts/{f}"))
    for q in QUESTIONS:
        out.append(("rmagent-so", f"scripts/questions/windows/{q}.ps1"))
        out.append(("rmagent-fr", f"scripts/questions/windows/{q}.ps1"))
    return out


def check_engine(fix: bool = False) -> list[dict]:
    canon = SKILLS / "rmagent-windows"
    drift = []
    for skill, rel in engine_pairs():
        c = canon / rel
        o = SKILLS / skill / rel
        if not c.exists():
            continue
        if not o.exists():
            drift.append({"skill": skill, "file": rel, "issue": "missing_in_skill"})
            continue
        if c.read_bytes() != o.read_bytes():
            drift.append({"skill": skill, "file": rel, "issue": "differs"})
            if fix:
                o.parent.mkdir(parents=True, exist_ok=True)
                o.write_bytes(c.read_bytes())
                print(f"  FIXED  {skill}/{rel}")
    return drift


def check_repo() -> list[dict]:
    """Live vs repo, via check_repo_sync.py (same directory)."""
    p = HERE / "check_repo_sync.py"
    if not p.exists():
        return [{"issue": "check_repo_sync.py missing"}]
    r = subprocess.run([sys.executable, str(p), "--json"],
                       capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return [{"issue": f"check_repo_sync.py failed: {r.stderr[:200]}"}]
    out = []
    for name, s in data.get("skills", {}).items():
        if not s.get("in_sync"):
            for k in s.get("differ", []):
                out.append({"skill": name, "file": k, "issue": "differs_from_live"})
            for k in s.get("live_only", []):
                out.append({"skill": name, "file": k, "issue": "live_only"})
            for k in s.get("repo_only", []):
                out.append({"skill": name, "file": k, "issue": "repo_only"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="rmagent drift checks (engine + repo)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fix", action="store_true",
                    help="engine only: copy rmagent-windows over drifted so/fr files")
    args = ap.parse_args()

    eng = check_engine(fix=args.fix)
    repo = check_repo()

    if args.json:
        print(json.dumps({"engine_drift": eng, "repo_drift": repo,
                          "in_sync": not eng and not repo}, indent=2))
    else:
        print(f"engine: {'IN SYNC' if not eng else f'{len(eng)} DRIFT'}")
        for d in eng:
            print(f"  {d['skill']:14} {d['file']:48} {d['issue']}")
        print(f"repo:   {'IN SYNC' if not repo else f'{len(repo)} DRIFT'}")
        for d in repo:
            print(f"  {d.get('skill','?'):14} {d.get('file','?'):48} {d['issue']}")
        if eng or repo:
            print("\nDRIFT DETECTED.")
            print("  engine: python3 sync_check.py --fix   (windows -> so/fr)")
            print("  repo:   python3 /tmp/sync_agent_skills.py   (live -> repo)")
    return 0 if not eng and not repo else 1


if __name__ == "__main__":
    sys.exit(main())
