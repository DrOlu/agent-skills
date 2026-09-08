#!/usr/bin/env python3
"""Rev 20 tests — rmagent-linux engine wiring.

The skill previously had payloads but NO engine entry point; its SKILL.md
claimed the Windows engine would be reused, but that engine rejects SSH.
Now: the five documented questions are allowlisted over an SSH door that
resolves the shared rmagent-so engine.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


print("== allowlist / payloads exist ==")
for q in ("attest", "sketch", "edges", "explain", "attackmap"):
    ok(q in lib.ALLOWED, f"{q} allowlisted")
    ok((HERE.parent / "questions" / "linux" / f"{q}.sh").exists(),
       f"{q}.sh payload exists")

print("== contract checks ==")
row = {"id": "lx1", "door": "ssh", "address": "127.0.0.1", "port": 22,
       "user": "nobody", "skills": ["attest"], "track": ["root"]}
r = lib.ask(row, "attest", timeout=8)
ok(isinstance(r, dict) and "ok" in r, "ssh ask returns the standard shape")
ok(r.get("ok") is False and r.get("hole"), "unreachable host -> honest hole")
r2 = lib.ask(row, "actuate", timeout=8)
ok(r2.get("ok") is False, "actuate refused")
row3 = dict(row, skills=["edges"])
r3 = lib.ask(row3, "attest", timeout=8)
ok(r3.get("ok") is False and "advertise" in str(r3.get("error")), "not-advertised refused")
# shared-engine cap semantics carry over
import importlib
shared = importlib.import_module("lib")
ok(shared.MAX_PULL_BYTES == 32 * 1024, "shared 32 KB cap inherited")
ok(hasattr(shared, "_cap_signal"), "signal-aware cap inherited")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — linux rev20 suite: ALL TESTS PASSED")
