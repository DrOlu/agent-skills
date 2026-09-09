#!/usr/bin/env python3
"""Lint a skill directory against the rmagent constitution.

    python3 check_constitution.py --dir ~/.agents/skills/rmagent-iso
    python3 check_constitution.py --dir ~/.agents/skills/rmagent-template

Exit 0 = clone is structurally honest. Live-validation is still on you.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check(skill_dir: Path) -> list[str]:
    fails: list[str] = []
    skill = skill_dir / "SKILL.md"
    if not skill.exists():
        return [f"missing SKILL.md in {skill_dir}"]
    text = _read(skill).lower()

    skip_watch = skill_dir.name in ("rmagent-actuate", "rmagent-redteam")
    if not skip_watch and "constitution" not in text and "watch only" not in text:
        fails.append("SKILL.md: no constitution / watch-only wording")
    if not skip_watch and "hole" not in text:
        fails.append("SKILL.md: never mentions holes")
    if "32" not in text and "capped" not in text:
        fails.append("SKILL.md: no cap / 32 KB wording")
    if "~/.claude/skills" in _read(skill):
        fails.append("SKILL.md: stale ~/.claude/skills path — use ~/.agents/skills")
    # Scripts named in SKILL.md must exist (linux advertised census/hunt it didn't ship).
    for m in re.finditer(r"scripts/([a-zA-Z0-9_./-]+\.py)", _read(skill)):
        rel = m.group(0)
        if not (skill_dir / rel).exists() and not (skill_dir / "scripts" / Path(rel).name).exists():
            fails.append(f"SKILL.md names {rel} but file missing")

    lib = None
    for cand in (skill_dir / "scripts" / "lib.py", skill_dir / "scripts" / "lib_skeleton.py"):
        if cand.exists():
            lib = cand
            break
    if lib is None:
        if skill_dir.name in ("rmagent-actuate", "rmagent-redteam"):
            pass  # uses so engine / drill — not a witness
        else:
            fails.append("no scripts/lib.py (or lib_skeleton.py)")
    else:
        ltxt = _read(lib)
        if "ALLOWED" not in ltxt and "ask(" not in ltxt:
            fails.append(f"{lib.name}: no ALLOWED / ask()")
        if "actuate" not in ltxt.lower():
            fails.append(f"{lib.name}: actuate not mentioned (must refuse)")
        if "MAX_PULL_BYTES" not in ltxt and "32 * 1024" not in ltxt and "32768" not in ltxt:
            fails.append(f"{lib.name}: no 32 KB cap constant")
        if "hole" not in ltxt.lower():
            fails.append(f"{lib.name}: hole never used")
        # Grain firewall: identity skills must not allowlist app ETW names.
        name = skill_dir.name
        app_names = ("apptrace", "appslow", "apperrors", "appnet", "appproc", "appsysmon")
        ident_names = ("attest", "sketch", "edges", "explain")
        if name in ("rmagent-so", "rmagent-windows") and any(a in ltxt.split("ALLOWED", 1)[-1][:800] for a in app_names if f'"{a}"' in ltxt or f"'{a}'" in ltxt):
            # only fail if they appear inside ALLOWED set, not comments later
            allowed_blob = ltxt[ltxt.find("ALLOWED"):ltxt.find("PHASE0_SKILLS") if "PHASE0_SKILLS" in ltxt else ltxt.find("ALLOWED")+800]
            if any(f'"{a}"' in allowed_blob or f"'{a}'" in allowed_blob for a in app_names):
                fails.append(f"{lib.name}: identity skill ALLOWED contains app grain names")
        if name == "rmagent-at":
            allowed_blob = ltxt[ltxt.find("ALLOWED"):ltxt.find("PHASE0_SKILLS") if "PHASE0_SKILLS" in ltxt else ltxt.find("ALLOWED")+400]
            if any(f'"{a}"' in allowed_blob for a in ident_names):
                fails.append(f"{lib.name}: at ALLOWED contains identity grain names")
        if name == "rmagent-fr":
            allowed_blob = ltxt[ltxt.find("ALLOWED"):ltxt.find("PHASE0_SKILLS") if "PHASE0_SKILLS" in ltxt else ltxt.find("ALLOWED")+400]
            if "attest" in allowed_blob and "ALLOWED = set()" not in allowed_blob:
                fails.append(f"{lib.name}: fr must not knock (ALLOWED should be empty)")
        # REV 20 (P1): fail-closed contracts the linter can actually prove.
        # A comment saying "actuate refused" used to satisfy the check.
        # Now the parse path must mark empty/garbage output as NOT ok, and
        # the skeleton must not fake a sighted attest.
        if "def _parse" in ltxt or "def parse" in ltxt:
            empty_block = ltxt[ltxt.find("def _parse"):] if "def _parse" in ltxt else ltxt[ltxt.find("def parse"):]
            block = empty_block[:1800]
            if 'ok": True, "data": {"raw"' in block or "'ok': True, 'data': {'raw'" in block:
                fails.append(f"{lib.name}: _parse returns ok/raw on empty or garbage "
                             "output — must be a hole")
        if lib.name == "lib_skeleton.py":
            if '"blind_check": "unknown"' in ltxt and '"ok": True' in ltxt:
                fails.append("lib_skeleton.py: skeleton attest returns ok=True with "
                             "unknown sightedness — must be a hole / not-implemented")

    tests = list(skill_dir.glob("scripts/test_*.py")) + list(skill_dir.glob("scripts/test*.py"))
    if not tests and skill_dir.name != "rmagent-template":
        fails.append("no scripts/test_*.py")

    examples = (skill_dir / "EXAMPLES.md").exists() or (skill_dir / "examples").exists()
    if not examples:
        fails.append("no EXAMPLES.md or examples/")

    for yml in list(skill_dir.glob("*.yaml")) + list(skill_dir.glob("**/*.yaml")):
        if "node_modules" in str(yml):
            continue
        y = _read(yml)
        if re.search(r"(?i)^\s*password\s*:", y, re.M):
            fails.append(f"{yml.relative_to(skill_dir)}: password: in yaml")

    ps1 = list(skill_dir.glob("scripts/**/*.ps1")) + list(skill_dir.glob("scripts/questions/**/*.ps1"))
    if ps1:
        budget = list(skill_dir.glob("scripts/test_budget.py"))
        skill_has_budget = "8191" in text or budget
        if not skill_has_budget:
            fails.append(".ps1 present but no 8191 / test_budget.py note")

    # Only flag *created* rings (AutoLogger, SPAN/PCAP ingest), not "Sysmon ring" prose.
    needs_teardown = any(k in text for k in ("autologger", "tcpdump", "pcap", "erspan", "--apply"))
    if "span" in text and "jsonl" in text:
        needs_teardown = True
    if needs_teardown and "teardown" not in text and "mop" not in text:
        fails.append("created-ring/SPAN mentioned but no MOP/teardown wording")

    attest = "attest" in text or "blind" in text
    if not attest:
        fails.append("no attest / blind_check in SKILL.md")

    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args(argv)
    d = Path(args.dir).resolve()
    fails = check(d)
    if fails:
        print(f"FAIL {d}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"ok {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
