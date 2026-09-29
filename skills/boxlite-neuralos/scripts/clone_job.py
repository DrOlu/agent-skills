#!/usr/bin/env python3
"""Clone a neuralOS template box and run a prompt in a disposable microVM.

usage:
  clone_job.py --template neuralos-template --name job-001 \
      [--prompt "what's it like in Lagos right now?"] \
      [--program my_tools.py]      # in-box program; may contain __PROMPT__
      [--keep]                     # leave the job box running
      [--ask]                      # run ask.py style: program is an instance dir
"""
import argparse
import asyncio
import json
import os
import sys
import time

import boxlite

DEFAULT_PROGRAM = r'''
import json, os
os.environ.setdefault("NEEDLE_TELEMETRY", "0")
os.environ.setdefault("DO_NOT_TRACK", "1")
import needle

@needle.tool(triggers=["what is the weather", "weather in a city", "what is it like"])
def get_weather(city: str) -> dict:
    "Get the current weather for a city."
    return {"city": city, "temp_c": 27, "sky": "clear"}

@needle.tool(triggers=["add two numbers", "add numbers", "sum"])
def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b

agent = needle.Needle(tools=[get_weather, add])
print(json.dumps(agent.run(__PROMPT__), default=str))
'''

ASK_PROGRAM = r'''
import json, os, sys
os.environ.setdefault("NEEDLE_TELEMETRY", "0")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.chdir(__DIR__)
sys.path.insert(0, __DIR__)
import subprocess
r = subprocess.run([sys.executable, "ask.py", __DIR__, __PROMPT__],
                   capture_output=True, text=True)
print(r.stdout[-4000:])
if r.returncode: print(r.stderr[-1000:])
'''


async def _drain(stream):
    out = []
    async for line in stream:
        out.append(line)
    return "".join(out)


async def run(box, cmd, args=None, timeout=900):
    ex = await box.exec(cmd, args, timeout_secs=timeout)
    so = asyncio.create_task(_drain(ex.stdout()))
    se = asyncio.create_task(_drain(ex.stderr()))
    res = await ex.wait()
    return res.exit_code, await so, await se


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt", default="what's it like in Lagos right now?")
    ap.add_argument("--program", help="host .py file to run in the box instead of the demo")
    ap.add_argument("--instance-dir", help="in-box instance dir for --ask (default /opt/chinook)")
    ap.add_argument("--ask", action="store_true", help="delegate to ask.py inside the box")
    ap.add_argument("--keep", action="store_true", help="leave the job box running")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    rt = boxlite.Boxlite.default()
    tpl = await rt.get(a.template)

    t = time.time()
    job = await tpl.clone_box(name=a.name)
    print(f"[job] cloned '{a.template}' -> '{a.name}' in {time.time()-t:.2f}s")
    t = time.time()
    await job.start()
    print(f"[job] started in {time.time()-t:.1f}s")

    try:
        if a.program:
            await job.copy_in(a.program, "/tmp/job_program.py")
            program = open(a.program).read()
            program = program.replace("__PROMPT__", json.dumps(a.prompt))
            code, out, err = await run(job, "python3", ["-c", program], timeout=a.timeout)
        elif a.ask:
            d = a.instance_dir or "/opt/chinook"
            code, out, err = await run(job, "python3", ["ask.py", d, a.prompt], timeout=a.timeout)
        else:
            program = DEFAULT_PROGRAM.replace("__PROMPT__", json.dumps(a.prompt))
            code, out, err = await run(job, "python3", ["-c", program], timeout=a.timeout)

        print(f"[job] exit={code}")
        print("=== result ===")
        print((out or "").strip()[:4000])
        if (err or "").strip():
            print("=== stderr (tail) ===")
            print(err.strip()[-600:])
    finally:
        if not a.keep:
            await job.stop()
            print(f"[job] '{a.name}' stopped (clone; safe to delete).")
        else:
            print(f"[job] '{a.name}' left RUNNING.")


if __name__ == "__main__":
    asyncio.run(main())
