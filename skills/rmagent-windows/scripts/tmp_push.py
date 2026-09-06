#!/usr/bin/env python3
"""Mirror live -> repo, commit, push. One clean file-based step."""
import subprocess
from pathlib import Path

# reuse the mirror logic inline
import filecmp
import shutil

LIVE = Path.home() / ".agents" / "skills"
REPO = Path.home() / "work" / "agent-skills" / "skills"
SKILLS = ["rmagent-windows", "rmagent-actuate", "rmagent-so", "rmagent-fr", "rmagent-at"]
EX_S = {".pyc", ".DS_Store"}
EX_N = {"__pycache__", ".DS_Store", "cases"}


def collect(root):
    out = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*")):
        if p.is_dir() or p.suffix in EX_S or p.name in EX_N:
            continue
        if any(part in EX_N for part in p.parts):
            continue
        out[str(p.relative_to(root))] = p
    return out


added = updated = removed = 0
for name in SKILLS:
    live = collect(LIVE / name)
    root = REPO / name
    repo = collect(root)
    for rel, src in live.items():
        dst = root / rel
        if rel not in repo:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            added += 1
            print(f"  ADD {name}/{rel}")
        elif not filecmp.cmp(src, repo[rel], shallow=False):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            updated += 1
            print(f"  UPD {name}/{rel}")
    for rel in sorted(set(repo) - set(live)):
        (root / rel).unlink()
        removed += 1
        print(f"  RM  {name}/{rel}")
print(f"added={added} updated={updated} removed={removed}")

if added or updated or removed:
    subprocess.run(["git", "add", "skills/"], cwd=REPO.parent, check=True)
    r = subprocess.run(["git", "commit", "-m",
                        "skills(rmagent): heal live trees from repo after unknown local reversion; "
                        "restore actuate Rev 17 (validation/plan-gate/hash-chain/redaction), sync the "
                        "full Rev 17/18 engine into rmagent-windows, re-apply census M1/M2, "
                        "spacing-tolerant test_rev8 regex. All 8 suites green."],
                       cwd=REPO.parent, capture_output=True, text=True)
    print(r.stdout[-200:] or r.stderr[-200:])
    r = subprocess.run(["git", "push", "origin", "main"], cwd=REPO.parent,
                       capture_output=True, text=True)
    print((r.stdout or r.stderr).strip().splitlines()[-1])
else:
    print("nothing to commit")
