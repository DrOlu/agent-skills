#!/usr/bin/env python3
"""check_repo_drift — live vs repo drift for EVERY published skill.

The rmagent-only check (check_repo_sync.py) missed the reactorpro updates
three times in a row: the repo lags while the live tree moves, and nothing
surfaced it. This generalises the check to the whole published set.

The watched set is defined by the REPO, not by live: every directory under
skills/ that contains a SKILL.md is a published skill. Live-only skills
(experiments, personal) are ignored — they are not published, so they cannot
drift.

For each published skill:
  - files that differ            -> OUT OF SYNC (the repo is stale)
  - files live-only              -> NEW (live has files the repo lacks)
  - files repo-only              -> STALE (repo has files live removed)

Exit 1 on any drift. `--json` for machine use. `--quiet` prints only drift.

Usage:
  python3 check_repo_drift.py
  python3 check_repo_drift.py --json
  python3 check_repo_drift.py --only reactorpro-gateway-setup
  python3 check_repo_drift.py --fix          # live -> repo (add/update/remove)
"""
from __future__ import annotations
import argparse, filecmp, json, shutil, sys
from pathlib import Path

LIVE = Path.home() / ".agents" / "skills"
REPO = Path.home() / "work" / "agent-skills" / "skills"

EXCLUDE_DIRS = {"__pycache__", ".git", ".DS_Store", "node_modules", ".venv",
                "venv", "cases", "baselines", "agent-baselines"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".DS_Store", ".swp"}
EXCLUDE_NAMES = {".DS_Store"}


def collect(root: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if p.suffix in EXCLUDE_SUFFIX or p.name in EXCLUDE_NAMES:
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out[str(p.relative_to(root))] = p
    return out


def published_skills(only: str | None = None) -> list[str]:
    if not REPO.exists():
        return []
    names = []
    for d in sorted(REPO.iterdir()):
        if not d.is_dir() or d.name in EXCLUDE_DIRS:
            continue
        if not (d / "SKILL.md").exists():
            continue
        if only and d.name != only:
            continue
        names.append(d.name)
    return names


def check_one(name: str) -> dict:
    live, repo = collect(LIVE / name), collect(REPO / name)
    differ = [k for k in sorted(set(live) & set(repo))
              if not filecmp.cmp(live[k], repo[k], shallow=False)]
    live_only = sorted(set(live) - set(repo))
    repo_only = sorted(set(repo) - set(live))
    return {
        "skill": name,
        "in_sync": not (differ or live_only or repo_only),
        "live_files": len(live),
        "repo_files": len(repo),
        "differ": differ,
        "new_in_live": live_only,
        "stale_in_repo": repo_only,
        # a published skill with no live counterpart cannot be compared
        "live_missing": not (LIVE / name).exists(),
    }


def fix_one(name: str) -> tuple[int, int, int]:
    live, repo = collect(LIVE / name), collect(REPO / name)
    a = u = r = 0
    for rel, src in live.items():
        dst = REPO / name / rel
        if rel not in repo:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            a += 1
        elif not filecmp.cmp(src, repo[rel], shallow=False):
            shutil.copy2(src, dst)
            u += 1
    for rel in sorted(set(repo) - set(live)):
        (REPO / name / rel).unlink()
        r += 1
    return a, u, r


def main() -> int:
    ap = argparse.ArgumentParser(description="live vs repo drift, all published skills")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print only drifting skills")
    ap.add_argument("--only", help="check a single skill by name")
    ap.add_argument("--fix", action="store_true", help="copy live -> repo for drifting skills")
    args = ap.parse_args()

    names = published_skills(args.only)
    if not names:
        print("no published skills found (repo missing or empty?)")
        return 1

    results = [check_one(n) for n in names]
    drift = [r for r in results if not r["in_sync"]]

    if args.fix:
        for r in drift:
            if r["live_missing"]:
                print(f"  SKIP {r['skill']}: no live copy to sync from")
                continue
            a, u, rm = fix_one(r["skill"])
            print(f"  FIXED {r['skill']}: +{a} ~{u} -{rm}")
        # re-check
        results = [check_one(n) for n in names]
        drift = [r for r in results if not r["in_sync"]]

    if args.json:
        print(json.dumps({
            "watched": len(names),
            "out_of_sync": len(drift),
            "in_sync": not drift,
            "skills": results,
        }, indent=2))
        return 0 if not drift else 1

    if args.quiet:
        for r in drift:
            print(f"{r['skill']}: differ={len(r['differ'])} new={len(r['new_in_live'])} "
                  f"stale={len(r['stale_in_repo'])}")
        if not drift:
            print(f"all {len(names)} published skills in sync")
        return 0 if not drift else 1

    print(f"watched {len(names)} published skills (repo-defined set)")
    for r in results:
        if r["in_sync"] and not args.only:
            continue
        if r["in_sync"]:
            print(f"  in sync      {r['skill']}")
            continue
        if r["live_missing"]:
            print(f"  NO LIVE COPY {r['skill']}  (repo-only; cannot compare)")
            continue
        print(f"  OUT-OF-SYNC  {r['skill']}  live={r['live_files']} repo={r['repo_files']} "
              f"differ={len(r['differ'])} new={len(r['new_in_live'])} stale={len(r['stale_in_repo'])}")
        for k in r["differ"][:8]:
            print(f"      DIFFERS  {k}")
        for k in r["new_in_live"][:8]:
            print(f"      NEW      {k}")
        for k in r["stale_in_repo"][:8]:
            print(f"      STALE    {k}")

    print()
    if drift:
        print(f"{len(drift)} of {len(names)} published skills OUT OF SYNC")
        print("  fix: python3 check_repo_drift.py --fix   (live -> repo)")
        return 1
    print(f"all {len(names)} published skills in sync (live == repo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
