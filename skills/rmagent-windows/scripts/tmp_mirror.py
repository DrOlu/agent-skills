"""Mirror live -> repo (the sync step, file-based)."""
import filecmp
import shutil
from pathlib import Path

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
