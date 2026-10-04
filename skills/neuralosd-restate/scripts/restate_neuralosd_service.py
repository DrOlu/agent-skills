#!/usr/bin/env python3
"""Durable Restate service wrapping a neuralosd instance HTTP door.

Env:
  NEURALOSD_URL   instance ask endpoint (default http://127.0.0.1:8878/ask)
  SERVICE_PORT    handler server port (default 9090)

Register with Restate:
  curl -X POST localhost:9070/deployments -H 'content-type: application/json' \
       -d '{"uri": "http://127.0.0.1:9090"}'

Invoke (durable - journaled, retried, resumable):
  curl -X POST localhost:8080/WemaAsk/ask  -d '"how many open incidents"'
  curl -X POST localhost:8080/WemaTriage/triage
"""
import json
import os
import urllib.request

import restate

WEMA = os.environ.get("NEURALOSD_URL", "http://127.0.0.1:8878/ask")
PORT = int(os.environ.get("SERVICE_PORT", "9090"))


def ask_sync(question: str) -> dict:
    body = json.dumps({"question": question}).encode()
    r = urllib.request.Request(WEMA, data=body,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read().decode())


service = restate.Service(name="WemaAsk")

triage_svc = restate.Service(name="WemaTriage")


@service.handler()
async def ask(ctx: restate.Context, question: str) -> dict:
    """One durable neuralosd ask; result journaled on completion."""
    return await ctx.run(f"ask:{question}", lambda: ask_sync(question))


@triage_svc.handler()
async def triage(ctx: restate.Context) -> dict:
    """Three journaled asks; each step resumes independently on retry."""
    overview = await ctx.run("overview", lambda: ask_sync("itsm overview"))
    critical = await ctx.run("critical", lambda: ask_sync("critical incidents"))
    bygroup = await ctx.run(
        "bygroup",
        lambda: ask_sync("which support group has the most open incidents"))
    return {"overview": overview.get("results"),
            "critical": critical.get("results"),
            "busiest_group": bygroup.get("results")}


@triage_svc.handler()
async def nightly_report(ctx: restate.Context) -> str:
    """Human-readable summary suitable for cron/email/chat delivery."""
    ov = await ctx.run("overview", lambda: ask_sync("itsm overview"))
    res = (ov.get("results") or [{}])[0]
    lines = ["Wema BMC daily summary:"]
    for k in ("open_incidents", "open_changes", "open_tasks",
              "open_work_orders", "open_problems"):
        if k in res:
            lines.append(f"- {k.replace('_', ' ')}: {res[k]}")
    return "\n".join(lines)


app = restate.app(services=[service, triage_svc])

if __name__ == "__main__":
    import hypercorn.asyncio
    import hypercorn
    import asyncio
    conf = hypercorn.Config()
    conf.bind = [f"0.0.0.0:{PORT}"]
    asyncio.run(hypercorn.asyncio.serve(app, conf))
