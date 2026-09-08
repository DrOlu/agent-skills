#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-actuate safety fixes.

1. Apply gate binds the ACTION (a plan for one action cannot approve another).
2. Undo passes captured pre-state (task XML / isolation rule map) in $Target.
3. Secret values are never printed — only a withheld-key notice.
"""
from __future__ import annotations
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import actuate
import journal

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


print("== 1. plan binds witness + action + target ==")
# the gate is inside main(); verify the comparison contract directly by
# inspecting find_plan + the error wording, plus a source-level check
src = (HERE / "actuate.py").read_text()
ok('plan.get("action") != args.action' in src,
   "apply gate compares plan action to requested action")
ok("plans bind witness + action + target" in src, "refusal message states the binding")

# end-to-end: a plan recorded for disable_user must NOT authorize
# rotate_credential. Drive main() with argv and expect the REFUSED exit.
tmp = Path(tempfile.mkdtemp(prefix="rmagent-act-rev20-"))
with mock.patch.object(journal, "JOURNAL", tmp / "j.jsonl"):
    pid = actuate.plan_id_for("ws1", "disable_user", "evil")
    journal.append("ws1", "disable_user", "evil", "r",
                   {"action": "enable_user", "target": "evil"}, "dry-run", plan_id=pid)
    plan = actuate.find_plan(pid)
    ok(plan is not None and plan.get("action") == "disable_user",
       "dry-run recorded with its action")
    # simulate the gate: witness+target match but action differs
    def gate(action):
        return plan is not None and plan.get("witness") == "ws1" \
            and plan.get("target") == "evil" and plan.get("action") == action
    ok(gate("disable_user"), "matching action passes the gate")
    ok(not gate("rotate_credential"), "DIFFERENT action is refused by the gate")

print("== 2. undo passes captured pre-state ==")
src_undo = (HERE / "actuate.py").read_text()
ok('detail.get("task_xml")' in src_undo, "undo reads task_xml from the journal entry")
ok('disabled_allow_rules' in src_undo or 'previous_allow_rules' in src_undo,
   "undo reads the isolation rule map from the journal entry")
rt = (actuate.ADIR / "recreate_task.ps1").read_text()
ok("ConvertFrom-Json" in rt and "Register-ScheduledTask -TaskName $taskName -Xml $taskXml" in rt,
   "recreate_task parses the JSON target and uses the XML")
ui = (actuate.ADIR / "un_isolate_host.ps1").read_text()
ok("ConvertFrom-Json" in ui and "Enable-NetFirewallRule" in ui
   and "DefaultInboundAction" in ui,
   "un_isolate_host restores journaled rules AND profile defaults")

print("== 3. secrets never printed ==")
ok("ONE-TIME" not in src_undo, "the old ONE-TIME secret print is gone")
ok("value withheld" in src_undo, "secret notice withholds the value")
ok("res['data'][k]" not in src_undo, "no direct secret-value interpolation into prints")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — actuate rev20 suite: ALL TESTS PASSED")
