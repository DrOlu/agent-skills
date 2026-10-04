#!/usr/bin/env python3
"""Register the deployment and run durable invocations.

Usage:
  python3 register_and_invoke.py --register
  python3 register_and_invoke.py --ask "how many worklog entries exist"
  python3 register_and_invoke.py --triage
"""
import argparse
import json
import time
import urllib.request

INGRESS = "http://localhost:8080"
ADMIN = "http://localhost:9070"
SERVICE_URL = "http://127.0.0.1:9090"


def post(url, payload):
    body = json.dumps(payload).encode()
    r = urllib.request.Request(url, data=body,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=600) as resp:
        return json.loads(resp.read().decode())


def register():
    out = post(f"{ADMIN}/deployments", {"uri": SERVICE_URL})
    svcs = [s["name"] for s in out.get("services", [])]
    print("registered:", out.get("id"), "services:", svcs)


def ask(question):
    t0 = time.time()
    out = post(f"{INGRESS}/WemaAsk/ask", question)
    print(f"[{time.time()-t0:.1f}s] {question}")
    print("   ", json.dumps(out.get("results", out), default=str)[:220])


def triage():
    t0 = time.time()
    out = post(f"{INGRESS}/WemaTriage/triage", {})
    print(f"triage in {time.time()-t0:.1f}s")
    for k in ("overview", "critical", "busiest_group"):
        print(f"  {k}:", json.dumps(out.get(k), default=str)[:200])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--ask")
    ap.add_argument("--triage", action="store_true")
    a = ap.parse_args()
    if a.register:
        register()
    if a.ask:
        ask(a.ask)
    if a.triage:
        triage()
    if not (a.register or a.ask or a.triage):
        print("nothing to do: use --register / --ask Q / --triage")
