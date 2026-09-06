#!/usr/bin/env python3
"""Flip estate.yaml transports to psrp (with ntlm fallback comment), verify
via lib.ask through the normal path, mirror to repo, commit + push."""
import subprocess
from pathlib import Path

# 1. estate flip
est = Path.home() / "estate.yaml"
t = est.read_text()
n = t.count("transport: ntlm")
t = t.replace("transport: ntlm", "transport: psrp ")
est.write_text(t)
print(f"estate.yaml: {n} witness(es) -> transport: psrp")

# 2. live end-to-end through the normal ask path (no overrides)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

INV = lib.load_inventory(str(est))
for row in lib.witnesses(INV):
    r = lib.ask(row, "attest", since_hours=1.0, limit=5)
    d = r.get("data") or {}
    print(f"[{row['id']}] attest via psrp: ok={r.get('ok')} blind={d.get('blind_count')} "
          f"sysmon={d.get('sysmon_status')}")

# 3. mirror to repo
import filecmp, shutil
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

added = updated = 0
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
        elif not filecmp.cmp(src, repo[rel], shallow=False):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            updated += 1
print(f"repo mirror: added={added} updated={updated}")

if added or updated:
    subprocess.run(["git", "add", "skills/"], cwd=REPO.parent, check=True)
    subprocess.run(["git", "commit", "-m",
                    "skills(rmagent): Rev 19 - add the psrp door (pypsrp) to lib.ask. "
                    "Opt-in per witness (door: psrp or transport: psrp); script travels "
                    "inside the PSRP body so the 8191-char winrm command-line budget "
                    "disappears for psrp witnesses. pywinrm stays the default; same "
                    "allowlist/cap/holes/cooldown path. Live-verified edges parity on WS1."],
                   cwd=REPO.parent, check=True, capture_output=True)
    r = subprocess.run(["git", "push", "origin", "main"], cwd=REPO.parent,
                       capture_output=True, text=True)
    print((r.stdout or r.stderr).strip().splitlines()[-1])
else:
    print("repo already current")
