#!/usr/bin/env python3
"""Rev 20 regression tests — rmagent-fr fixes.

1. STC round-trips the fanout budget (was silently reset to 0).
2. trace_merge imports cleanly and reports unreachable remotes as holes.
3. record_ask persists the full envelope (capped/cap_note/ok), not bare data.
4. correlate._load_answers unwraps envelopes and keeps provenance.
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stc as stc_mod
import lib
import correlate

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


print("== 1. STC fanout budget round-trips ==")
S = stc_mod.STC(case="CASE-1", principal="Administrator", depth=2, fanout=2)
enc = S.encode()
ok("fanout=2" in enc, f"fanout serialized: {enc}")
D = stc_mod.STC.decode(enc)
ok(D.fanout == 2, f"fanout survives decode (got {D.fanout})")
ok(D.depth == 2, "depth still round-trips")
D2 = D.sibling()
ok(D2.fanout == 3, "sibling increments fanout")
try:
    D2.sibling()
    ok(False, "fanout budget enforced at 3")
except ValueError:
    ok(True, "fanout budget enforced at 3")
D3 = stc_mod.STC.decode(stc_mod.STC(case="C", principal="p", fanout=3).encode())
try:
    D3.sibling()
    ok(False, "decoded exhausted fanout stays exhausted")
except ValueError:
    ok(True, "decoded exhausted fanout stays exhausted")

print("== 2. trace_merge import + hole status ==")
import trace_merge
ok(hasattr(trace_merge, "pull_and_merge"), "trace_merge imports (NameError fixed)")
merged, status = trace_merge.pull_and_merge(["user@dead.invalid.example"], case=None)
ok(status.get("user@dead.invalid.example", {}).get("hole") == "remote-unreachable-or-empty",
   f"unreachable remote reported as a hole: {status}")

print("== 3. record_ask persists the envelope ==")
tmp = Path(tempfile.mkdtemp(prefix="rmagent-fr-rev20-"))
row = {"id": "ws1", "plane": "endpoint"}
result = {"ok": True, "data": {"logons": [{"lid": "0x1"}]},
          "capped": True, "cap_note": "trimmed"}
lib.record_ask(tmp, row, "edges", result)
legacy = json.loads((tmp / "answers" / "ws1__edges.json").read_text())
ok(legacy.get("capped") is True, "legacy-mirrored file carries envelope")
ok(legacy.get("data", {}).get("logons"), "legacy-mirrored file carries data")
stampeds = sorted((tmp / "answers").glob("ws1__edges__*.json"))
ok(len(stampeds) == 1, "timestamped envelope written")
env = json.loads(stampeds[0].read_text())
ok(env.get("cap_note") == "trimmed", "cap_note preserved")
ok(env.get("t"), "ask timestamp preserved")

# a failed ask keeps its hole provenance
lib.record_ask(tmp, row, "pslogs", {"ok": False, "error": "boom",
                                    "hole": {"why": "boom"}})
env2 = json.loads((tmp / "answers" / "ws1__pslogs.json").read_text())
ok(env2.get("ok") is False and env2.get("hole", {}).get("why") == "boom",
   "failed ask persists hole provenance")

print("== 4. correlate unwraps envelopes ==")
loaded = correlate._load_answers(tmp)
ok("ws1__edges" in loaded, "envelope file loads under legacy key")
ok(loaded["ws1__edges"].get("logons"), "bare data accessible to joiners")
ok(loaded["ws1__edges"].get("_envelope", {}).get("capped") is True,
   "trim provenance retained via _envelope")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — fr rev20 suite: ALL TESTS PASSED")
