#!/usr/bin/env python3
"""Graded 10-question benchmark — the needle-3-replacement acceptance test.

Usage:
    python3 bench_stress.py --instance-dir ./wema-bmc [--model qwen3.5:9b]

Set: 7 answerable questions (counts, caged lookups, derived metrics) +
3 traps where the ONLY correct behaviour is none_of_these.
Acceptance: >= 9/10 with honest refusals on the traps and no fabricated args.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ollama_client import constrained_pick  # noqa: E402

QUESTIONS = [
    ("how many open incidents", "open_incidents"),
    ("show me critical and high priority incidents", "critical_high_incidents"),
    ("what is the status of incident INC000000077173", "incident_lookup"),
    ("break down the work orders by status", "workorder_status_breakdown"),
    ("find person login sandra.olaniyi@wemabank.com", "person_lookup"),
    ("how many sla measurements are there", "sla_measurements"),
    ("what is the ratio of open problems to open incidents",
     "open_problems_to_incidents_ratio"),
    ("how many worklog entries exist", "worklog_count"),
    ("which support group has the most open incidents",
     "open_incidents_by_group"),
    ("are there more open problems or open work orders",
     "compare_open_counts"),
]
ARG_KEYS = {"incident_lookup": ("inc",), "person_lookup": ("email",),
            "incident_search": ("keyword",),
            "compare_open_counts": ("pair",),
            "list_open_incidents": ("limit",),
            "worklog_for_incident": ("inc",)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-dir", required=True)
    ap.add_argument("--model",
                    default=os.environ.get("NEURALOS_OLLAMA_MODEL",
                                           "qwen3.5:9b"))
    args = ap.parse_args()
    inst = os.path.abspath(args.instance_dir)
    menu = json.load(open(os.path.join(inst, "needle_menu.json")))
    menu = menu["menu"] if isinstance(menu.get("menu"), list) else menu["menu"]
    descriptions = {p["name"]: p.get("description", "") for p in menu}

    sys.path.insert(0, inst)
    os.chdir(inst)
    import probes as probes_mod  # noqa: E402
    by_name = {f.__name__: f for f in probes_mod.PROBES}

    results, ok = [], 0
    for q, expect in QUESTIONS:
        pick, wall = constrained_pick(q, [n for n, _ in QUESTIONS],
                                      descriptions=descriptions,
                                      model=args.model)
        name = pick.get("probe")
        verdict = "OK" if name == expect else (
            "REFUSED" if name == "none_of_these" else f"MISROUTE -> {name}")
        fabricated = any(v for k, v in pick.items()
                         if k != "probe" and isinstance(v, str)
                         and v.lower() not in q.lower())
        if verdict != "OK" and name != "none_of_these":
            fabricated = True  # any arg on a misroute is fabricated
        answer = None
        if verdict == "OK":
            ok += 1
            kwargs = {k: pick[k] for k in ARG_KEYS.get(name, ()) if k in pick}
            try:
                answer = by_name[name](**kwargs)
            except Exception as e:  # noqa: BLE001
                answer = f"EXEC-ERROR: {e}"
        results.append({"q": q, "expect": expect, "picked": name,
                        "verdict": verdict, "fabricated_arg": fabricated,
                        "seconds": round(wall, 1),
                        "answer": json.dumps(answer, default=str)[:160]})
        print(f"[{verdict}] ({wall:.1f}s) {q}", flush=True)

    refusals = sum(1 for r in results if r["verdict"] == "REFUSED")
    fabrications = sum(1 for r in results if r["fabricated_arg"])
    passed = ok >= 9 and fabrications == 0
    print(f"\nSCORE: {ok}/10 OK, {refusals} honest refusals, "
          f"{fabrications} fabricated args -> "
          f"{'ACCEPTED as needle-3 replacement' if passed else 'REJECTED'}")
    json.dump(results, open("bench_results.json", "w"), indent=2,
              default=str)


if __name__ == "__main__":
    main()
