#!/usr/bin/env python3
"""report.py — one-page IR report skeleton from a case directory.

Reads chain.jsonl, timeline.jsonl and correlation findings (if the hunt ran)
and writes IR_REPORT.md. The skeleton states what is KNOWN, what is a HOLE
and what is OPEN — an honest report never fills gaps with narrative.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import chain as chainmod

def generate(case: Path):
    case = Path(case)
    ok, n, bad = chainmod.verify(case)
    answers = sorted((case / "answers").glob("*.json")) if (case / "answers").is_dir() else []
    tl = case / "timeline.jsonl"
    rows = [json.loads(l) for l in open(tl)] if tl.exists() else []
    holes = []
    holesf = case / "holes.jsonl"
    if holesf.exists():
        holes = [json.loads(l).get("why", "?") for l in open(holesf)]
    md = [f"# IR REPORT — {case.name}", "",
          f"_Generated from the case directory; every number traces to a chained artifact._", "",
          "## Chain of custody",
          f"- {n} chained actions — **{'VERIFIED, hashes intact' if ok else 'CORRUPT: ' + ', '.join(bad)}**",
          f"- {'Court-ready' if ok and not bad else 'NOT court-ready until the chain verifies'}", "",
          "## Collections", ""]
    for f in answers:
        md.append(f"- `{f.name}`")
    md += ["", "## Timeline highlights",
           f"- {len(rows)} normalized records; "
           + (f"span {rows[0]['ts']} → {rows[-1]['ts']}" if rows else "no records"), ""]
    corr = case / "correlation.json"
    if corr.exists():
        try:
            c = json.load(open(corr))
            md += ["## Correlated findings", ""]
            for f in c.get("findings", []):
                md.append(f"- **[{f.get('severity','?')}]** {f.get('kind')} — {f.get('detail','')[:200]} "
                          f"(rank {f.get('triage_rank','?')}, recommended: {', '.join(f.get('recommended_actions', []) or ['—'])})")
            md.append("")
        except Exception:
            pass
    if holes:
        md += ["## Holes (honest gaps)", ""] + [f"- {h}" for h in holes] + [""]
    md += ["## Open actions", "",
           "- [ ] validate the timeline against the operator's known-good activity",
           "- [ ] route each correlated finding through the actuate gate if response is needed",
           "- [ ] preserve the case directory (chain verified) before any cleanup", ""]
    out = case / "IR_REPORT.md"
    out.write_text("\n".join(md))
    print(f"[report] {out}")
    return out

if __name__ == "__main__":
    generate(Path(sys.argv[1] if len(sys.argv) > 1 else "cases/ir"))
