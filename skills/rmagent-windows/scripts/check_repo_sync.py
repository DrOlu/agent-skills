#!/usr/bin/env python3
"""check_repo_sync — are the LIVE rmagent skills identical to the repo copy?

The live skills in ~/.agents/skills are the source of truth: they are what
actually runs. The repo (~/work/agent-skills) is the published copy. This
script fails loudly when the two diverge, which has happened repeatedly —
most recently the repo sat at rev 11 while live was at rev 15, and nobody
noticed because nothing compared them.

Complements sync_check.py:
  sync_check.py      — engine drift BETWEEN skills (windows vs so vs fr)
  check_repo_sync.py — drift BETWEEN live and the repo, across all 8 skills

Usage:
  python3 check_repo_sync.py          # human-readable, exit 1 on drift
  python3 check_repo_sync.py --json

Excludes runtime state that is EXPECTED to be live-only:
  __pycache__/, cases/, baselines/, agent-baselines/, *.pyc, .DS_Store
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

LIVE = Path.home() / ".agents" / "skills"
REPO = Path.home() / "work" / "agent-skills" / "skills"

SKILLS = ["rmagent-windows", "rmagent-actuate", "rmagent-redteam",
          "rmagent-so", "rmagent-fr", "rmagent-linux", "rmagent-ao", "rmagent-at"]

EXCLUDE_DIRS = {"__pycache__", "cases", "baselines", "agent-baselines", ".git"}
EXCLUDE_SUFFIX = {".pyc", ".DS_Store"}


def collect(root: Path) -> dict:
    """{relpath: bytes} for every file, excluding runtime state."""
    out = {}
    if not root.exists():
        return out
    for r, dirs, files in root.walk():
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if Path(f).suffix in EXCLUDE_SUFFIX or f == ".DS_Store":
                continue
            p = r / f
            try:
                out[str(p.relative_to(root))] = p.read_bytes()
            except Exception:
                out[str(p.relative_to(root))] = b"<unreadable>"
    return out


def check() -> dict:
    per_skill, total_bad = {}, 0
    for name in SKILLS:
        live, repo = collect(LIVE / name), collect(REPO / name)
        differ = sorted(k for k in set(live) & set(repo) if live[k] != repo[k])
        only_live = sorted(set(live) - set(repo))
        only_repo = sorted(set(repo) - set(live))
        bad = bool(differ or only_live or only_repo)
        if bad:
            total_bad += 1
        per_skill[name] = {
            "in_sync": not bad,
            "live_files": len(live), "repo_files": len(repo),
            "differ": differ, "live_only": only_live, "repo_only": only_repo,
        }
    return {"in_sync": total_bad == 0, "skills_out_of_sync": total_bad,
            "skills": per_skill}


def main() -> int:
    ap = argparse.ArgumentParser(description="live vs repo sync check")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = check()

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        for name, s in r["skills"].items():
            status = "in sync" if s["in_sync"] else "OUT-OF-SYNC"
            print(f"  {status:12s} {name:20s} live={s['live_files']:3d} "
                  f"repo={s['repo_files']:3d} differ={len(s['differ'])} "
                  f"live-only={len(s['live_only'])} repo-only={len(s['repo_only'])}")
            for k in s["differ"][:5]:
                print(f"      DIFFERS   {k}")
            for k in s["live_only"][:5]:
                print(f"      LIVE-ONLY {k}")
            for k in s["repo_only"][:5]:
                print(f"      REPO-ONLY {k}")
        print()
        if r["in_sync"]:
            print(f"ALL {len(SKILLS)} rmagent skills in sync (live == repo)")
        else:
            print(f"{r['skills_out_of_sync']} skill(s) OUT OF SYNC — "
                  f"run /tmp/sync_agent_skills.py to copy live -> repo")
    return 0 if r["in_sync"] else 1


if __name__ == "__main__":
    sys.exit(main())
