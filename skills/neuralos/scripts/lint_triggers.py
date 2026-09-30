#!/usr/bin/env python3
"""Trigger collision linter — simulate lexical retrieval for every trigger
and flag triggers that would route to the WRONG probe (rank-1 != owner).

This is the CI gate for operating rule 8's companion: menu changes can
degrade existing picks, and this catches it WITHOUT running the model.

usage: lint_triggers.py <needle_menu.json> [--top N] [--max-triggers 40]
exit : 0 clean | 1 collisions found
"""
import argparse
import json
import re
import sys

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
    ap.add_argument("menu", help="needle_menu.json path")
    ap.add_argument("--top", type=int, default=8,
                    help="top-K size used by the retrieval front-end")
    ap.add_argument("--max-triggers", type=int, default=40,
                    help="bloat warning threshold per probe")
    a = ap.parse_args()

    menu = json.load(open(a.menu, encoding="utf-8"))
    collisions, soft, hard, bloat = [], [], [], []
    for probe in menu:
        name = probe["name"]
        if len(probe.get("triggers", [])) > a.max_triggers:
            bloat.append((name, len(probe["triggers"]), a.max_triggers))
        for trig in probe.get("triggers", []):
            qt = tokens(trig)
            scored = sorted(((score_probe(p, qt), p) for p in menu),
                            key=lambda x: -x[0])
            winners = [p["name"] for s, p in scored[:a.top] if s > 0]
            if winners and winners[0] != name:
                if name in winners:
                    # SOFT: owner still in top-K — the model sees it and can
                    # disambiguate with the rest of the question
                    soft.append((name, trig, winners[0]))
                else:
                    # HARD: owner not even retrieved — guaranteed mis-route
                    hard.append((name, trig, winners[0]))

    print(f"menu: {len(menu)} probes, "
          f"{sum(len(p.get('triggers', [])) for p in menu)} triggers")
    for name, n, cap in bloat:
        print(f"BLOAT  {name}: {n} triggers (>{cap}) — compact to patterns; "
              f"bloat degrades unrelated picks (verified live)")
    for owner, trig, wrong in hard:
        print(f"HARD    owner={owner} trigger={trig!r} -> {wrong!r} "
              f"(owner NOT in top-{a.top} — guaranteed mis-route)")
    for owner, trig, wrong in soft:
        print(f"soft    owner={owner} trigger={trig!r} -> {wrong!r} "
              f"(owner in top-{a.top}; model disambiguates w/ context)")
    print(f"\ncollisions: {len(hard)} hard, {len(soft)} soft, {len(bloat)} bloat")
    if hard:
        print("fix HARD collisions first (reword, remove, or add a "
              "distinguishing token to the owner).")
        raise SystemExit(1)
    print("no HARD collisions — retrieval puts every owner in context.")
    if soft:
        print(f"note: {len(soft)} soft collisions — the model disambiguates "
              f"with fuller questions; watch menu_gaps for real misses.")


if __name__ == "__main__":
    main()
