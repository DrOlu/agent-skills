#!/usr/bin/env python3
"""Cook a persistent neuralOS template Box.

Creates (or upgrades) a box with neuralOS preinstalled, verifies it with a
real tool call, and stops it with auto_delete=0 so the disk (engine + weights)
survives. Later, clone this box for jobs.

usage:
  cook_template.py --name neuralos-template [--image python:3.12-slim]
      [--cpus 1] [--memory-mib 1024] [--disk-gb 6]
      [--packages "pymysql pydantic"]      # extra pip packages for the template
"""
import argparse
import asyncio
import time

import boxlite

VERIFY_PROGRAM = r'''
import json, os
os.environ.setdefault("NEEDLE_TELEMETRY", "0")
os.environ.setdefault("DO_NOT_TRACK", "1")
import needle

@needle.tool(triggers=["add two numbers", "add numbers", "sum"])
def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b

agent = needle.Needle(tools=[add])
r = agent.run("add 2 and 3")
res = r.get("results")
if isinstance(res, list):
    first = res[0] if res else {}
    tool_result = first.get("sum", first) if isinstance(first, dict) else first
else:
    tool_result = res            # executed tools may return the value directly
print(json.dumps({"version": needle.__version__,
                  "tool_result": tool_result,
                  "type": r.get("type"),
                  "confidence": r.get("confidence")}))
'''


async def _drain(stream):
    out = []
    async for line in stream:
        out.append(line)
    return "".join(out)


async def run(box, cmd, args=None, timeout=1800):
    ex = await box.exec(cmd, args, timeout_secs=timeout)
    so = asyncio.create_task(_drain(ex.stdout()))
    se = asyncio.create_task(_drain(ex.stderr()))
    res = await ex.wait()
    return res.exit_code, await so, await se


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="neuralos-template")
    ap.add_argument("--image", default="python:3.12-slim")
    ap.add_argument("--cpus", type=int, default=1)
    ap.add_argument("--memory-mib", type=int, default=1024)
    ap.add_argument("--disk-gb", type=int, default=6)
    ap.add_argument("--packages", default="", help="extra pip packages, space separated")
    a = ap.parse_args()

    rt = boxlite.Boxlite.default()
    got = await rt.get_or_create(
        boxlite.BoxOptions(image=a.image, auto_delete=0, cpus=a.cpus,
                           memory_mib=a.memory_mib, disk_size_gb=a.disk_gb),
        name=a.name)
    box = got[0] if isinstance(got, tuple) else got
    await box.start()

    pkgs = "neuralos" + ((" " + a.packages) if a.packages.strip() else "")
    t = time.time()
    code, out, err = await run(box, "python", ["-m", "pip", "install", "--upgrade", "--no-cache-dir"] + pkgs.split())
    print(f"[cook] pip install ({pkgs}) exit={code} in {time.time()-t:.0f}s")
    if code:
        print((err or out)[-1200:]); raise SystemExit(code)

    code, out, err = await run(box, "python", ["-c", VERIFY_PROGRAM], timeout=600)
    print(f"[cook] verify exit={code}")
    print("       ", out.strip()[:400])
    if code:
        print((err or "")[-800:]); raise SystemExit(code)
    if "5" not in out and "sum" not in out:
        print("[cook] WARN: tool call did not visibly return 5 — inspect output above")

    await box.stop()
    print(f"[cook] template '{a.name}' cooked and stopped (auto_delete=0 → disk persists).")
    print("       clone it with: clone_job.py --template", a.name)


if __name__ == "__main__":
    asyncio.run(main())
