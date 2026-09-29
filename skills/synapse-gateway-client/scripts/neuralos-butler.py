#!/usr/bin/env python3
"""Generic neuralOS butler — exposes local neuralOS instance(s) as read-only
mesh skills. Agentd-free: runs anywhere Python + nats-py exist.

Modes (auto-detected):
  multi  BUTLER_INSTANCES_DIR = dir of instance subdirs (each with needle_menu.json)
         serves: butler.list / butler.query {instance, question, k?}
  single BUTLER_INSTANCE_DIR  = one instance dir (with needle_menu.json)
         serves: butler.list / butler.query {question, k?}

Other env:
  BUTLER_AGENT_ID   mesh id                    (default reactorpro/butler)
  BUTLER_MESH_URL   NATS URL                   (default nats://127.0.0.1:4222)
  BUTLER_PYTHON     python that runs ask.py    (default sys.executable)
  BUTLER_ASK_TIMEOUT seconds per ask.py call   (default 120)

Constitution: READ-ONLY. 32 KB cap. Honest holes. Watchdog recycles a dead
subscription (2 missed self-probes -> exit -> service manager restarts).
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import nats

AGENT_ID = os.environ.get("BUTLER_AGENT_ID", "reactorpro/butler")
URL = os.environ.get("BUTLER_MESH_URL", "nats://127.0.0.1:4222")
MAX_BYTES = 32 * 1024
ASK_TIMEOUT = int(os.environ.get("BUTLER_ASK_TIMEOUT", "120"))
PY = os.environ.get("BUTLER_PYTHON", sys.executable)

SINGLE = Path(os.environ.get("BUTLER_INSTANCE_DIR", ""))
MULTI = Path(os.environ.get("BUTLER_INSTANCES_DIR", ""))

if SINGLE.is_dir() and (SINGLE / "needle_menu.json").is_file():
    MODE, ROOT = "single", SINGLE
elif MULTI.is_dir():
    MODE, ROOT = "multi", MULTI
else:
    print("[butler] no instance dir found — set BUTLER_INSTANCE_DIR or "
          "BUTLER_INSTANCES_DIR", file=sys.stderr)
    sys.exit(1)

def _ask_path(inst_dir):
    """Generated fleets put ask.py either in the instance dir or the fleet root."""
    for cand in (inst_dir / "ask.py", inst_dir.parent / "ask.py"):
        if cand.is_file():
            return cand
    return inst_dir / "ask.py"


def _menu(inst_dir):
    m = json.loads((inst_dir / "needle_menu.json").read_text(encoding="utf-8"))
    return m if isinstance(m, list) else m.get("tools", [])


def _instances():
    return sorted(p.name for p in ROOT.iterdir()
                  if p.is_dir() and (p / "needle_menu.json").is_file())


def _run_ask(inst_dir, question, k=None):
    t0 = time.time()
    ask = _ask_path(inst_dir)
    cmd = [PY, str(ask), str(inst_dir), question]
    if MODE == "single":
        cmd = [PY, str(ask), inst_dir.name, question]
    if k:
        cmd += ["--k", str(k)]
    try:
        # ask.py resolves siblings (instance.py, bridge.py) from ITS dir,
        # so the subprocess must run with the ask.py parent as cwd.
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=ASK_TIMEOUT, cwd=str(ask.parent))
        out = (p.stdout or "").strip()
        if p.returncode != 0 and not out:
            return {"ok": False, "error": (p.stderr or "non-zero exit")[:500],
                    "elapsed_s": round(time.time() - t0, 1)}
        return {"ok": True, "result": out[:MAX_BYTES],
                "elapsed_s": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {ASK_TIMEOUT}s", "hole": True,
                "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}


def _args(req):
    """Caller args ride in payload["message"] (synapse-client) or
    payload["input"] (gateway RequestPayload); fall back to the payload."""
    for key in ("message", "input"):
        m = req.get(key)
        if isinstance(m, dict):
            return m
    return {}


def h_list(req):
    if MODE == "multi":
        rows = [{"instance": i, "probes": len(_menu(ROOT / i))}
                for i in _instances()]
        return {"ok": True, "agent": AGENT_ID, "mode": MODE, "count": len(rows),
                "instances": rows,
                "note": "read-only; call butler.query {instance, question}"}
    probes = [{"name": t.get("name"),
               "description": (t.get("description") or "")[:160]}
              for t in _menu(ROOT) if isinstance(t, dict)]
    return {"ok": True, "agent": AGENT_ID, "mode": MODE,
            "instance": ROOT.name, "count": len(probes), "probes": probes,
            "note": "read-only; call butler.query {question}"}


def h_query(req):
    question = str(req.get("question", "")).strip()
    if not question:
        return {"ok": False, "error": "question is required"}
    if MODE == "multi":
        inst = str(req.get("instance", "")).strip()
        if inst not in _instances():
            return {"ok": False,
                    "error": f"unknown instance {inst!r}; known: {_instances()}"}
        inst_dir = ROOT / inst
    else:
        inst_dir = ROOT
    k = req.get("k")
    out = _run_ask(inst_dir, question, k)
    out.update({"answered_by": AGENT_ID,
                "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return out


def route(req):
    skill = str(req.get("skill", "")).split(".")[-1]
    handler = {"list": h_list, "query": h_query}.get(skill)
    if handler is None:
        return {"ok": False,
                "error": f"unknown skill {skill!r}; served: butler.list/query"}
    return handler(_args(req))


def envelope(kind, payload=None, error=None, task_id=None, in_reply_to=None):
    env = {"v": "1.0.0", "id": uuid.uuid4().hex, "type": kind, "from": AGENT_ID,
           "to": "", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if task_id:
        env["task_id"] = task_id
    if in_reply_to:
        env["in_reply_to"] = in_reply_to
    if error:
        env["error"] = error
    else:
        env["payload"] = payload if payload is not None else {}
    return env


SKILLS = [
    {"id": "butler.list", "name": "butler.list",
     "description": "List the neuralOS instance(s) this butler serves"},
    {"id": "butler.query", "name": "butler.query",
     "description": "Ask a plain-language question of a local neuralOS instance "
                    "(read-only). args: {instance?, question, k?}. Up to "
                    f"{ASK_TIMEOUT}s."},
]


async def watchdog(nc):
    misses = 0
    n = 0
    while True:
        await asyncio.sleep(60)
        n += 1
        try:
            fut = nc.request(f"mesh.agent.{AGENT_ID}.inbox",
                             json.dumps({"v": "1.0.0", "type": "request",
                                         "from": AGENT_ID,
                                         "payload": {"skill": "butler.list",
                                                     "task_id": f"wd-{n}",
                                                     "message": {}}}).encode(),
                             timeout=20)
            await asyncio.wait_for(fut, timeout=20)
            if misses:
                print(f"[wd] recovered after {misses} miss(es)", flush=True)
            misses = 0
        except Exception as e:  # noqa: BLE001
            misses += 1
            print(f"[wd] miss {misses} ({type(e).__name__})", flush=True)
            if misses >= 2:
                print("[wd] dead subscription — exiting for service-manager restart",
                      flush=True)
                os._exit(1)


async def run_once():
    nc = await nats.connect(URL, name=AGENT_ID.replace("/", "-"))
    try:
        await nc.publish("mesh.registry.register", json.dumps(envelope(
            "register", {"id": AGENT_ID, "name": "neuralOS butler",
                         "description": "Read-only neuralOS instance queries",
                         "capabilities": ["neuralos", "data"], "skills": SKILLS,
                         "availability": "online"})).encode())
    except Exception as e:  # noqa: BLE001
        print(f"[registry] skipped: {e}", flush=True)

    async def on_msg(msg):
        try:
            env = json.loads(msg.data.decode())
            req = env.get("payload", env)
            task_id = req.get("task_id") or env.get("task_id")
            try:
                result = route(req)
            except Exception as e:  # noqa: BLE001
                result = None
                if msg.reply:
                    err = envelope("respond", None,
                                   {"code": 5001, "message": str(e)[:300],
                                    "retryable": True}, task_id, env.get("id"))
                    await nc.publish(msg.reply, json.dumps(err).encode())
                    return
            if msg.reply:
                rep = envelope("respond", {"result": result},
                               task_id=task_id, in_reply_to=env.get("id"))
                await nc.publish(msg.reply, json.dumps(rep).encode())
        except Exception as e:  # noqa: BLE001
            print(f"[on_msg] {type(e).__name__}: {e}", flush=True)
        finally:
            try:
                await msg.ack()
            except Exception:
                pass

    await nc.subscribe(f"mesh.agent.{AGENT_ID}.inbox", cb=on_msg)
    asyncio.ensure_future(watchdog(nc))
    inst = _instances() if MODE == "multi" else [ROOT.name]
    print(f"[butler] serving as {AGENT_ID} on {URL} · mode={MODE} · "
          f"instances={inst}", flush=True)
    while True:
        await asyncio.sleep(3600)


async def main():
    while True:
        try:
            await run_once()
        except Exception as e:  # noqa: BLE001
            print(f"[butler] crash ({type(e).__name__}: {e}); restart in 5s",
                  flush=True)
        await asyncio.sleep(5)


asyncio.run(main())
