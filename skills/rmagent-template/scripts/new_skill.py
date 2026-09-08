#!/usr/bin/env python3
"""Stamp a new rmagent-* skill tree from this template.

    python3 new_skill.py --name rmagent-net --title "Circuit Flight Recorder" \
        --grain "circuit_id + time window" \
        --sensor "SNMP allowlisted GETs + syslog JSONL ring" \
        --plane netops --scope "PE routers we administer" \
        --out ~/.agents/skills/rmagent-net
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def _sub(text: str, mapping: dict[str, str]) -> str:
    for k, v in mapping.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def stamp(args: argparse.Namespace) -> Path:
    name = args.name.strip()
    if not name.startswith("rmagent-"):
        raise SystemExit("name must start with rmagent-")
    out = Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"{out} exists (pass --force to overwrite files we stamp)")
    slug = name.replace("rmagent-", "").replace("-", "_")
    mapping = {
        "NAME": name,
        "TITLE": args.title,
        "GRAIN": args.grain,
        "SENSOR": args.sensor,
        "PLANE": args.plane,
        "SCOPE": args.scope or f"the {args.plane} estate we administer",
        "SLUG": slug,
    }

    (out / "scripts" / "questions" / "linux").mkdir(parents=True, exist_ok=True)
    (out / "scripts" / "questions" / "windows").mkdir(parents=True, exist_ok=True)
    (out / "examples").mkdir(parents=True, exist_ok=True)

    skill_tmpl = (HERE / "templates" / "SKILL.md.tmpl").read_text()
    (out / "SKILL.md").write_text(_sub(skill_tmpl, mapping))
    (out / "SAFETY.md").write_text(_sub((HERE / "templates" / "SAFETY.md.tmpl").read_text(), mapping))
    shutil.copy(HERE / "templates" / "estate.example.yaml", out / "estate.example.yaml")
    shutil.copy(HERE / "scripts" / "lib_skeleton.py", out / "scripts" / "lib.py")

    hunt = f'''#!/usr/bin/env python3
"""CLI — named questions only."""
from __future__ import annotations
import argparse, json, sys
from lib import ALLOWED, ask

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", help="one of: " + ", ".join(sorted(ALLOWED)))
    ap.add_argument("--inventory", default="estate.example.yaml")
    args, rest = ap.parse_known_args(argv)
    ans = ask(args.question)
    print(json.dumps(ans, indent=2, default=str))
    return 1 if ans.get("hole") and ans.get("reason") == "not-allowlisted" else 0

if __name__ == "__main__":
    sys.exit(main())
'''
    (out / "scripts" / "hunt.py").write_text(hunt)

    test = f'''#!/usr/bin/env python3
"""Skeleton tests for {name} — extend with domain fixtures."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ask

def main() -> int:
    n = f = 0
    def check(c, m):
        nonlocal n, f
        n += 1
        print(("  ok  " if c else "  FAIL ") + m)
        if not c:
            f += 1
    a = ask("actuate")
    check(a.get("hole") and a.get("reason") == "not-allowlisted", "actuate rejected")
    b = ask("baseline", n=3)
    check(b.get("reason") == "baseline-n-too-small", "n<30 baseline is a hole")
    t = ask("attest")
    check(t.get("question") == "attest", "attest exists")
    print(f"{{n-f}}/{{n}} passed")
    return 1 if f else 0

if __name__ == "__main__":
    sys.exit(main())
'''
    (out / "scripts" / f"test_{slug}.py").write_text(test)

    (out / "EXAMPLES.md").write_text(
        f"# {name} examples\n\n"
        f"Fill after the first fixture exists.\n\n"
        f"```bash\npython3 scripts/hunt.py attest\npython3 scripts/test_{slug}.py\n```\n"
    )
    (out / "examples" / "question-table.md").write_text(
        (HERE / "examples" / "question-table.md").read_text()
        if (HERE / "examples" / "question-table.md").exists()
        else "# fill the question table before payloads\n"
    )
    print(str(out))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--grain", required=True)
    ap.add_argument("--sensor", required=True)
    ap.add_argument("--plane", required=True)
    ap.add_argument("--scope", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    stamp(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
