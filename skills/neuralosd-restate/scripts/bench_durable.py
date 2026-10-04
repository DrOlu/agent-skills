#!/usr/bin/env python3
"""Timing benchmark: N triage runs (durable, journaled)."""
import argparse
import json
import time
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    times = []
    for i in range(a.runs):
        body = json.dumps({}).encode()
        r = urllib.request.Request("http://localhost:8080/WemaTriage/triage",
                                   data=body,
                                   headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(r, timeout=600) as resp:
            out = json.loads(resp.read().decode())
        wall = time.time() - t0
        times.append(wall)
        ov = (out.get("overview") or [{}])[0]
        print(f"run {i+1}: {wall:.2f}s | open_incidents={ov.get('open_incidents')} "
              f"open_changes={ov.get('open_changes')}")
    if times:
        print(f"\nmin {min(times):.2f}s | avg {sum(times)/len(times):.2f}s | "
              f"max {max(times):.2f}s")


if __name__ == "__main__":
    main()
