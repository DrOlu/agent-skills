#!/usr/bin/env python3
"""Confidence calibration harness — learn per-probe accept thresholds.

Runs the golden question bank through ask.py, records the engine confidence
per question, and computes the highest gate that keeps every known-correct
answer (per-probe, instead of the demo_server's global 0.80). Writes
calibration.json for the orchestrator to consume.

usage: calibrate.py --golden golden.json [--port 8877] [--host 127.0.0.1] \
         [--out calibration.json]
Requires the instance web service (serve.py / demo_server.py) running.
"""
import argparse
import json
import urllib.request


def ask(base, q):
    req = urllib.request.Request(base + "/ask",
                                 data=json.dumps({"question": q}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="golden.json")
    ap.add_argument("--base", default="http://127.0.0.1:8877")
    ap.add_argument("--out", default="calibration.json")
    a = ap.parse_args()

    bank = json.load(open(a.golden, encoding="utf-8"))
    per_probe = {}
    for item in bank["items"]:
        try:
            d = ask(a.base, item["q"])
        except Exception as e:
            print(f"SKIP  {item['q']!r}: {e}")
            continue
        probe = d.get("tool") or d.get("probe")
        conf = d.get("confidence")
        if probe is None or conf is None:
            continue
        per_probe.setdefault(probe, []).append(conf)
        print(f"{probe:<38} conf={conf:.3f}  {item['q']!r}")

    calibration = {}
    for probe, confs in sorted(per_probe.items()):
        # keep every known-correct answer: gate = min observed confidence,
        # with a floor so a single lucky 0.0 doesn't disable the gate
        calibration[probe] = round(max(min(confs), 0.05), 3)

    json.dump({"version": 1,
               "note": "gate = min observed confidence across known-correct "
                       "golden answers; floor 0.05",
               "gates": calibration},
              open(a.out, "w"), indent=2)
    print(f"\ncalibration written: {a.out} ({len(calibration)} probes)")


if __name__ == "__main__":
    main()
