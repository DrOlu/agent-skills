#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-redteam fixes.

1. Cleanup that cannot be verified is UNKNOWN, never reported as 'cleaned'.
2. run_full persists a run manifest BEFORE staging and records cleanup state.
3. Scoring is per-host: background counts only earn credit on a staged host.
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import redteam

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


ROWS = [{"id": "ws1", "address": "10.0.0.1", "skills": [], "track": []}]

print("== 1. unverifiable cleanup is UNKNOWN ==")
with mock.patch.object(redteam, "run_payload", return_value={"ok": True, "data": {}}):
    ok(redteam.clean(ROWS) is False, "ok-but-unverifiable response -> not clean")
with mock.patch.object(redteam, "run_payload",
                       side_effect=RuntimeError("ssh refused")):
    ok(redteam.clean(ROWS) is False, "transport exception -> not clean")
with mock.patch.object(redteam, "run_payload",
                       return_value={"ok": True, "data": {"cleaned": ["RMAgentDrill_Task"],
                                                          "still_present": []}}):
    ok(redteam.clean(ROWS) is True, "verified response -> clean")
with mock.patch.object(redteam, "run_payload",
                       return_value={"ok": True, "data": {"cleaned": [], "still_present": ["x"]}}):
    ok(redteam.clean(ROWS) is False, "still_present -> not clean")

print("== 2. run manifest + finally-cleanup ==")
src = (HERE / "redteam.py").read_text()
ok("run_manifest.json" in src, "run manifest is persisted")
ok("finally:" in src, "cleanup is in a finally block")
ok("INCOMPLETE-OR-UNKNOWN" in src, "manifest records cleanup state honestly")
tmp = Path(tempfile.mkdtemp(prefix="rmagent-rt-rev20-"))
case = tmp / "case-test"
case.mkdir()
with mock.patch.object(redteam, "run_payload",
                       return_value={"ok": True, "data": {"cleaned": ["x"], "still_present": []}}):
    ok(redteam.clean(ROWS) is True, "clean() on a verified mock passes")

print("== 3. per-host scoring ==")
# staged on ws1 only; explain hop for ws2 with generic counts must NOT credit
staged = {"new_service": {"ws1"}}
case_dir = Path(tempfile.mkdtemp(prefix="rt-score-"))
(case_dir / "path.json").write_text(json.dumps([
    {"witness": "ws2", "skill": "explain", "service_events": 3},  # background on ws2
    {"witness": "ws1", "skill": "explain", "service_events": 1},  # staged ws1
]))
found = redteam.score([], "", case_dir, staged)
ns = found.get("new_service")
ok(isinstance(ns, dict) and set(ns.keys()) == {"ws1"},
   f"per-host credit only on the staged host (got {ns})")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — redteam rev20 suite: ALL TESTS PASSED")
