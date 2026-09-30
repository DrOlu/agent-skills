#!/usr/bin/env python3
"""Resident ask daemon — one process, many asks (amortizes weights load).

Runs the standardized ask pipeline (from ask.py) in-process behind a tiny
HTTP server: POST /ask {"question": ...}. Solves the process-per-ask weights
reload cost while keeping the audit log, cache, results-gating and
deterministic fast path.

usage: python3 askd.py [--port 8877] [--dir /opt/chinook]
Run inside the sandbox (it binds 0.0.0.0 in-guest; publish via the runtime).
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8877)
ap.add_argument("--dir", default=os.getcwd())
a = ap.parse_args()
os.chdir(a.dir)
sys.path.insert(0, a.dir)

import ask as ask_module  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"ok": True, "mode": "resident-askd"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            question = str(payload.get("question") or "").strip()
        except Exception as exc:
            self._send(400, {"error": f"bad request: {exc}"})
            return
        if not question:
            self._send(400, {"error": "empty question"})
            return
        try:
            env = ask_module.ask_one(question)
            self._send(200, env)
        except SystemExit as exc:
            self._send(422, {"error": "no results produced",
                             "code": int(exc.code or 0)})
        except Exception as exc:
            self._send(500, {"error": str(exc)[:300]})


def main():
    print(f"neuralOS askd -> http://0.0.0.0:{a.port}/ask "
          f"(dir: {a.dir})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
