#!/usr/bin/env python3
"""Gap miner — Phase 5 (EXTEND) of the neuralos workflow.

Consumes an ask-audit log (ask_audit.jsonl, written by generated ask.py) or a
menu_gaps.jsonl (demo_server confidence-gated asks) and proposes:
  * triggers to add to the probe that retrieval ranked FIRST (it was the
    right family; the selector/retrieval just didn't have the phrasing)
  * flag questions where retrieval found NOTHING (candidate for a new probe)

Output: a reviewable proposal file (proposals.json + markdown summary).
This does NOT edit the menu — a human (or agent) reviews, applies, then
re-runs lint_triggers.py + the full selection suite.

usage: mine_gaps.py <audit.jsonl|menu_gaps.jsonl> --menu needle_menu.json \
         [--out proposals.json] [--min-conf 0.0]
"""
import argparse
import json
import re
import sys
from collections import defaultdict

STOP = set("the a an of in on for to and or is are was were what which who how "
           "many show me give list all with their from by at it its do does did "
           "i we you this that those these there have has had more than one not "
           "use between during along per into over under about their".split())


def tokens(text):
    return set(re.findall(r"[a-z0-9_]+", str(text).lower())) - STOP


def score_probe(probe, q_tokens):
    s = 0.0
    for trig in probe.get("triggers", []):
        s += 3.0 * len(q_tokens & tokens(trig))
    s += 1.0 * len(q_tokens & tokens(probe["name"].replace("_", " ")))
    s += 0.3 * len(q_tokens & tokens(probe.get("description", "")))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", help="ask_audit.jsonl or menu_gaps.jsonl")
    ap.add_argument("--menu", default="needle_menu.json")
    ap.add_argument("--out", default="proposals.json")
    a = ap.parse_args()

    menu = json.load(open(a.menu, encoding="utf-8"))
    by_name = {p["name"]: p for p in menu}

    new_triggers = defaultdict(set)   # probe -> {phrasings}
    new_probe_candidates = []         # questions retrieval found nothing for

    for line in open(a.log, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        q = (rec.get("question") or rec.get("normalized") or "").strip()
        if not q:
            continue
        retrieved = rec.get("candidates_retrieved") or rec.get("retrieved") or []
        if isinstance(retrieved, str):
            retrieved = [x.strip() for x in retrieved.strip("[]").split(",") if x.strip()]
        probe = rec.get("probe") or rec.get("picked") or rec.get("tool")
        conf = rec.get("confidence")

        if not retrieved:
            new_probe_candidates.append(q)
            continue
        # the rank-1 retrieved probe was the right FAMILY but the ask gated
        # or mis-fired -> propose the phrasing as a trigger for it
        owner = retrieved[0] if retrieved[0] in by_name else probe
        if owner in by_name:
            phrasing = re.sub(r"^(how about|what about|and |now )\s+", "", q,
                              flags=re.I).strip()
            new_triggers[owner].add(phrasing)

    proposals = {}
    for owner, trigs in sorted(new_triggers.items()):
        existing = set((by_name.get(owner) or {}).get("triggers", []))
        add = sorted(t for t in trigs if t not in existing)
        if add:
            proposals[owner] = add

    json.dump({"new_triggers": proposals,
               "new_probe_candidates": sorted(set(new_probe_candidates))},
              open(a.out, "w"), indent=2, ensure_ascii=False)

    print(f"proposed triggers for {len(proposals)} probe(s):")
    for owner, add in sorted(proposals.items()):
        print(f"  {owner}: +{len(add)} -> {add[:4]}")
    if new_probe_candidates:
        print(f"\n{len(new_probe_candidates)} question(s) retrieved NOTHING — "
              f"candidate for a NEW probe:")
        for q in sorted(set(new_probe_candidates))[:8]:
            print("  ?", q)
    print(f"\nwritten: {a.out} — review, apply to needle_menu.json/instance.py, "
          f"then re-run lint_triggers.py + the full selection suite.")


if __name__ == "__main__":
    main()
