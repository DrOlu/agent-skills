#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-ao fixes.

1. ALLOWED matches the SKILL.md question set (was: security questions).
2. SSH door works (was: "this skill is Windows-only").
3. Empty/unparseable answers are holes, never ok/raw.
4. Resolved secrets never leak back into os.environ.
"""
from __future__ import annotations
import json
import os
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


print("== 1. allowlist matches SKILL.md ==")
for q in ("agents", "agentstate", "agenttrace", "agentnet",
          "agentmodels", "agentdrift", "agentdeep"):
    ok(q in lib.ALLOWED, f"{q} is allowlisted")
ok("attest" not in lib.ALLOWED and "edges" not in lib.ALLOWED,
   "security questions are NOT the agent allowlist")

print("== 2. SSH door ==")
row = {"id": "mac", "door": "ssh", "address": "127.0.0.1", "port": 22,
       "user": "nobody", "skills": ["agents"], "track": ["root"], "os": "linux"}
r = lib.ask(row, "agents", timeout=8)
ok(isinstance(r, dict) and "ok" in r, "ssh door returns the standard shape")
ok(r.get("ok") is False and r.get("hole"), "unreachable ssh host -> honest hole (not an exception)")
ok("Windows-only" not in str(r.get("error")), "no more 'Windows-only' refusal")

# not-advertised still refused
row2 = dict(row, skills=["agenttrace"])
r2 = lib.ask(row2, "agents", timeout=8)
ok(r2.get("ok") is False and "advertise" in str(r2.get("error")), "not-advertised question refused")
# actuate refused
row3 = dict(row, skills=["agents"])
r3 = lib.ask(row3, "actuate", timeout=8)
ok(r3.get("ok") is False and "actuate" in str(r3.get("error")).lower(), "actuate refused")

print("== 3. parse honesty ==")
ok(lib._parse("")["ok"] is False, "empty -> hole")
ok(lib._parse("garbage not json")["ok"] is False, "garbage -> hole")
ok(lib._parse('banner\n{"a":1}')["data"] == {"a": 1}, "banner-prefixed JSON parses")

print("== 4. secrets never in os.environ ==")
ok(not any("RMAgent_" in k and k.endswith("_PASS") for k in os.environ
           if os.environ[k] == "definitely-not-a-real-password"),
   "no test password in env")
src = (HERE / "lib.py").read_text()
ok("os.environ[f\"RMAgent_{rid}_PASS\"] = pw" not in src,
   "the env write-back of resolved passwords is gone")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — ao rev20 suite: ALL TESTS PASSED")
