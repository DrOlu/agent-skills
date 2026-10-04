#!/usr/bin/env python3
"""instance_ollama_runtime.py — swap the needle 121M selector in a neuralOS
python-runtime instance for an Ollama-hosted model (think disabled).

Uses Ollama's NATIVE tool-calls path (not format-enums): 48 schemas run
without the grammar slowness. Bridge execution unchanged.

Usage (run with the interpreter that has the instance's deps: needle, bridge
imports, pymysql/openpyxl as needed):

  python3 instance_ollama_runtime.py --instance-dir DIR --question "..." \
      [--model qwen3.5:9b] [--execute]

Measured (chinook, 48 tools, qwen3.5:9b):
  - sibling discrimination BOTH ways: count probe vs list probe picked
    correctly on count-phrasing AND list-phrasing (with limit arg extracted)
  - warm ~4s per pick; cold ~30s (model load)
  - needle 3 baseline on the same set: picked the LIST probe for both
"""
import argparse
import importlib
import json
import os
import sys
import time
import urllib.request

import needle

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434/api/chat")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-dir", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--model",
                    default=os.environ.get("NEURALOS_OLLAMA_MODEL",
                                           "qwen3.5:9b"))
    ap.add_argument("--tools-module", default="instance",
                    help="module in the instance dir exposing TOOLS")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    inst = os.path.abspath(args.instance_dir)
    sys.path.insert(0, inst)
    os.chdir(inst)
    mod = importlib.import_module(args.tools_module)
    tools_list = list(mod.TOOLS)
    by_name = {f.__name__: f for f in tools_list}
    tools = [{"type": "function", "function": needle.build_schema(f)}
             for f in tools_list]

    body = json.dumps({
        "model": args.model, "think": False, "stream": False,
        "messages": [{"role": "system",
                      "content": "answer strictly from the menu probes"},
                     {"role": "user", "content": args.question}],
        "tools": tools,
        "options": {"temperature": 0},
    }).encode()
    r = urllib.request.Request(OLLAMA, data=body,
                               headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=300) as resp:
        out = json.loads(resp.read().decode())
    wall = time.time() - t0

    calls = (out.get("message") or {}).get("tool_calls") or []
    if not calls:
        print(json.dumps({"refused": True,
                          "reply": (out.get("message") or {})
                          .get("content", "")[:150],
                          "seconds": round(wall, 1)}, indent=1))
        return
    call = calls[0]["function"]
    name, fargs = call["name"], call.get("arguments") or {}
    result = {"tool": name, "args": fargs, "seconds": round(wall, 1)}

    if args.execute and name in by_name:
        try:
            result["results"] = by_name[name](**fargs)
        except Exception as e:  # noqa: BLE001
            result["results"] = f"EXEC-ERROR: {e}"
    print(json.dumps(result, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
