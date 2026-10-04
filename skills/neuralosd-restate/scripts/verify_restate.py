#!/usr/bin/env python3
"""Preflight: Restate server, deployment, durable invoke, journal."""
import json
import time
import urllib.request


def post(url, payload):
    body = json.dumps(payload).encode()
    r = urllib.request.Request(url, data=body,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=600) as resp:
        return json.loads(resp.read().decode())


def get(url):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode()


fails = []

# 1. server
try:
    print("server:", get("http://localhost:9070/health")[:60])
except Exception as e:
    fails.append(f"admin :9070 unreachable: {e}")
    print("FAIL server:", e)

# 2. deployment + services
try:
    deps = json.loads(get("http://localhost:9070/deployments"))
    svcs = [s["name"] for d in deps.get("deployments", deps.get("items", []))
            for s in d.get("services", [])]
    print("services:", svcs)
    if "WemaTriage" not in svcs and "WemaAsk" not in svcs:
        fails.append("Wema services not registered - run register_and_invoke --register")
except Exception as e:
    fails.append(f"deployments query failed: {e}")

# 3. durable invoke
try:
    t0 = time.time()
    out = post("http://localhost:8080/WemaAsk/ask",
               "how many open incidents")
    wall = time.time() - t0
    res = json.dumps(out.get("results"), default=str)[:140]
    print(f"durable ask OK ({wall:.1f}s): {res}")
    if wall > 60:
        fails.append(f"durable ask slow: {wall:.1f}s")
except Exception as e:
    fails.append(f"durable ask failed: {e} (is neuralosd serve up?)")

print("\nVERIFY:", "PASS" if not fails else f"FAIL - {fails}")
