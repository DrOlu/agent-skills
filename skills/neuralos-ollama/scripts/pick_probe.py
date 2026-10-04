#!/usr/bin/env python3
"""Constrained probe selection for a neuralosd instance — needle-3-free.

Usage:
    python3 pick_probe.py --instance-dir ./wema-bmc --question "how many open incidents"
    python3 pick_probe.py --instance-dir ./wema-bmc --question "..." --execute

Flow (code gate first, model second):
  1. lexical pre-scorer ranks all probes; keeps top-K (default 5)
  2. if top score is 0 -> refuse WITHOUT calling the model (the floor)
  3. otherwise the model picks among the top-K shortlist + none_of_these,
     constrained by Ollama format() — output is guaranteed valid JSON
  4. --execute runs the picked probe through the real bridge (cages apply)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ollama_client import constrained_pick  # noqa: E402

STOP = set("the a an of in on for to and or is are was were what which who "
           "how many show me give list all with their from by at it its do "
           "does did i we you this that those these there have has had more "
           "than one not use between during along per into over under about "
           "their".split())


def tokens(text):
    return set("".join(c if c.isalnum() else " " for c in text.lower())
               .split()) - STOP


def lexical_topk(question, menu, k=5):
    q = tokens(question)
    scored = []
    for p in menu:
        s = 0.0
        for trig in p.get("triggers", []):
            t = tokens(trig)
            if t:
                s = max(s, 3.0 * len(t & q))
        s += 1.0 * len(tokens(p["name"].replace("_", " ")) & q)
        s += 0.3 * len(tokens(p.get("description", "")) & q)
        scored.append((p, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-dir", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--model", default=os.environ.get("NEURALOS_OLLAMA_MODEL",
                                                      "qwen3.5:9b"))
    ap.add_argument("--execute", action="store_true",
                    help="run the picked probe through the real bridge")
    args = ap.parse_args()

    inst = os.path.abspath(args.instance_dir)
    menu = json.load(open(os.path.join(inst, "needle_menu.json")))
    menu = menu["menu"] if isinstance(menu.get("menu"), list) else menu["menu"]
    descriptions = {p["name"]: p.get("description", "") for p in menu}

    shortlist = lexical_topk(args.question, menu, k=args.top_k)
    if not shortlist or shortlist[0][1] <= 0:
        print(json.dumps({"refused": True,
                          "reason": "no probe matched (lexical floor)"}))
        return
    names = [p["name"] for p, _ in shortlist]

    pick, wall = constrained_pick(args.question, names,
                                  descriptions=descriptions, model=args.model)
    result = {"question": args.question, "shortlist": names,
              "pick": pick, "seconds": round(wall, 1)}

    if args.execute and pick.get("probe") not in (None, "none_of_these"):
        sys.path.insert(0, inst)
        os.chdir(inst)
        import re
        import probes as probes_mod  # noqa: E402
        fn = {f.__name__: f for f in probes_mod.PROBES}.get(pick["probe"])
        if fn is None:
            result["execution"] = f"unknown probe {pick['probe']}"
        else:
            # args come from the model, BUT anything the model omitted is
            # recovered from the question via the probe's own regex cage —
            # exactly what neuralosd's extract_args does. The model never
            # gets to skip a required caged argument.
            kwargs = {}
            meta = getattr(fn, "_probe", None)
            if meta is not None:
                for aname, spec in meta.args.items():
                    if pick.get(aname):
                        kwargs[aname] = pick[aname]
                    elif spec.get("type") == "pattern":
                        m = re.search(spec.get("pattern", ".+"), args.question,
                                      re.IGNORECASE)
                        if m and m.groups():
                            kwargs[aname] = m.group(1).strip()
                    elif spec.get("type") == "integer" and not spec.get(
                            "required", True) and spec.get("default") is not None:
                        kwargs[aname] = spec["default"]
            try:
                result["execution"] = fn(**kwargs)
            except Exception as e:  # noqa: BLE001
                result["execution"] = f"EXEC-ERROR: {e}"
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
