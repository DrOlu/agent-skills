#!/usr/bin/env python3
"""neuralOS verification suite for Microsandbox sandboxes.

Runs INSIDE a sandbox (copy in first: msb copy <skill>/scripts/suite.py SB:/root/suite.py)
and asks the demo server on 127.0.0.1:8877. Exits non-zero on any failure.

usage: python3 suite.py [--port 8877]
"""
import argparse
import json
import sys
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8877)
a = parser.parse_args()
BASE = f"http://127.0.0.1:{a.port}/ask"


def ask(q):
    req = urllib.request.Request(
        BASE, data=json.dumps({"question": q}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def rows_of(d):
    res = d.get("results")
    rows = []
    if isinstance(res, list) and res and isinstance(res[0], dict):
        rows = res[0].get("rows", []) or []
    return rows


def collect_countries(d):
    cs = set()

    def walk(x):
        if isinstance(x, dict):
            if "country" in x and isinstance(x["country"], str):
                cs.add(x["country"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d)
    return sorted(cs)


tests = [
    ("Ireland's top customers",   lambda b, r: bool(r) and all(x.get("country") == "Ireland" for x in r)),
    ("Brazil's best customers",   lambda b, r: bool(r) and all(x.get("country") == "Brazil" for x in r)),
    ("top customers in Brazil",   lambda b, r: bool(r) and all(x.get("country") == "Brazil" for x in r)),
    ("how about france",          lambda b, r: bool(r) and all(x.get("country") == "France" for x in r)),
    ("top customers",             lambda b, r: len(r) == 10 and len({x.get("country") for x in r}) > 3),
    ("how many tracks are in the database", lambda b, r: '"Track": 3503' in b),
    ("best performing employees", lambda b, r: "Jane Peacock" in b and "Steve Johnson" in b),
    ("which albums does AC/DC have", lambda b, r: "AC/DC" in b),
]

passed = 0
for q, check in tests:
    try:
        d = ask(q)
    except Exception as e:
        print(f"FAIL  {q!r}: request error {e}")
        continue
    raw = json.dumps(d, default=str)
    rows = rows_of(d)
    ok = bool(check(raw, rows))
    passed += ok
    cs = collect_countries(d)[:4]
    print(f"{'PASS' if ok else 'FAIL'}  {q!r:42s} rows={len(rows)} countries={cs}")

print(f"SUITE: {passed}/{len(tests)} PASS")
sys.exit(0 if passed == len(tests) else 1)
