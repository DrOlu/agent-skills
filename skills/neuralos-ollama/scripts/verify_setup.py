#!/usr/bin/env python3
"""Verify a machine is ready for neuralOS-ollama (needle-3-free operation).

Checks: Ollama reachable, model pulled, think:false honored (fast direct
answer), format() honored (impossible to emit an off-enum value).
Run: python3 verify_setup.py [--model qwen3.5:9b]
"""
import argparse
import time

from ollama_client import chat, constrained_pick


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:9b")
    args = ap.parse_args()
    model = args.model
    fails = []

    # 1. model reachable + pulled
    t0 = time.time()
    out, wall = chat(model, [{"role": "user",
                              "content": "Reply with exactly: hello"}],
                     num_predict=50, think=False)
    content = out.get("message", {}).get("content", "")
    print(f"[{'OK' if content else 'FAIL'}] model responds ({wall:.1f}s): "
          f"{content[:40]!r}")
    if not content:
        fails.append("model did not answer; is it pulled? did thinking eat "
                     "the budget? (client sends think:false)")

    # 2. format honored: off-enum value must be impossible
    pick, wall = constrained_pick("how many open incidents",
                                  ["open_incidents"],
                                  descriptions={"open_incidents":
                                                "count open incidents"},
                                  model=model)
    legal = pick.get("probe") in ("open_incidents", "none_of_these")
    print(f"[{'OK' if legal else 'FAIL'}] format constraint honored: "
          f"{pick} ({wall:.1f}s)")
    if not legal:
        fails.append("format constraint not honored")

    # 3. think:false honored: constrained pick must NOT take minutes
    if wall > 30:
        fails.append(f"constrained pick took {wall:.1f}s — thinking is probably "
                     "not disabled or the model fights the grammar")
        print(f"[FAIL] latency: {wall:.1f}s (expect < 30s warm)")
    else:
        print(f"[OK] latency: {wall:.1f}s")

    # 4. refusal lever present
    pick, _ = constrained_pick("how many incidents were submitted in the "
                               "last 7 days",
                               ["open_incidents", "open_incidents_by_group"],
                               descriptions={"open_incidents":
                                             "count currently open incidents",
                                             "open_incidents_by_group":
                                             "group open incidents by team"},
                               model=model)
    print(f"[{'OK' if pick.get('probe') == 'none_of_these' else 'WARN'}] "
          f"gap question -> {pick.get('probe')} (refusal lever is a judgment "
          "call, not a guarantee)")

    print("\nVERIFY:", "PASS" if not fails else f"FAIL — {fails}")


if __name__ == "__main__":
    main()
