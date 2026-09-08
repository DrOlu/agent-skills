#!/usr/bin/env python3
"""Rev 20 regression tests — honesty fixes for rmagent-so.

1. Empty/unparseable answers are holes, never clean data.
2. Critical-event escalation is EXACT on typed fields, never substring.
3. attackmap FP suppression is EXACT value matching, with a suppressed count.
4. shared-logonid is a candidate association, not a critical verdict.
5. patient-zero refuses to walk through unknown-sightedness witnesses.
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib
import correlate
import patient_zero

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


print("== 1. parse honesty ==")
r = lib._parse("")
ok(r.get("ok") is False and r.get("hole"), "empty stdout -> hole, not ok/raw")
r = lib._parse("not json at all !!")
ok(r.get("ok") is False, "unparseable stdout -> hole")
r = lib._parse('banner\n{"a":1}')
ok(r.get("ok") is True and r.get("data") == {"a": 1}, "banner-prefixed JSON still parses")

print("== 2. exact event-id escalation ==")
ok(lib._row_signal({"eid": "4688"}) == 2, "typed eid 4688 -> critical")
ok(lib._row_signal({"id": " 4104 "}) == 2, "typed id with whitespace -> critical")
ok(lib._row_signal({"event_id": 7045}) == 2, "numeric event_id -> critical")
ok(lib._row_signal({"msg": "contains 4688 somewhere"}) == 1, "substring in prose -> normal")
ok(lib._row_signal({"port": 4624}) == 1, "unrelated numeric field -> normal")
ok(lib._row_signal("not-a-dict") == 1, "non-dict row -> normal")

print("== 3. exact FP suppression ==")
data = {"findings": [
    {"t": "T1546.007", "c": 2, "v": ["netiohlp", "evil-dotnet-helper.dll"]},
    {"t": "T1546.007", "c": 1, "v": ["C:\\Windows\\System32\\netiohlp.dll"]},
]}
out = lib._filter_attackmap_fps(data)
f = out["findings"][0]
ok(f["v"] == ["evil-dotnet-helper.dll"], "substring-named helper SURVIVES (was suppressed before)")
ok(out["fp_suppressed"] == 3, "exact/known-good values suppressed and counted")
ok(out["found"] == 1, "found count reflects kept findings")
ok(lib._filter_attackmap_fps({"findings": []}).get("fp_suppressed") is None,
   "no suppression -> no counter")

print("== 4. shared-logonid is a candidate, not a verdict ==")
ROWS = [
    {"id": "ws1", "address": "10.0.0.1", "skills": ["edges"], "track": ["Administrator"]},
    {"id": "ws2", "address": "10.0.0.2", "skills": ["edges"], "track": ["Administrator"]},
]
answers = {
    "ws1__edges": {"logons": [{"lid": "0x123", "user": "Administrator",
                               "t": "2026-09-08T10:00:00Z", "src": "10.9.9.9"}]},
    "ws2__edges": {"logons": [{"lid": "0x123", "user": "Administrator",
                               "t": "2026-09-08T10:05:00Z", "src": "10.9.9.9"}]},
}
res = correlate.correlate(answers, ROWS)
kind = next((f for f in res["findings"] if f["kind"].startswith("shared-logonid")), None)
ok(kind is not None, "logonid join still fires")
ok(kind and kind["kind"] == "shared-logonid-candidate", "kind renamed to shared-logonid-candidate")
ok(kind and kind["severity"] == "warning", "severity downgraded critical -> warning")
ok(kind and kind.get("evidence_class") == "candidate-association", "evidence_class recorded")
ok(kind and kind.get("recommended_actions") == [], "no auto-actuate on a counter coincidence")

print("== 5. patient-zero sightedness honesty ==")
INV = {"witnesses": [
    {"id": "ws2", "address": "10.0.0.2", "skills": ["attest", "edges"], "track": ["Administrator"]},
    {"id": "ws1", "address": "10.0.0.1", "skills": ["attest", "edges"], "track": ["Administrator"]},
]}
# 5a. attest missing blind_count -> blind-unknown, no origin claim
def ask_no_blind(row, skill, **kw):
    if skill == "attest":
        return {"ok": True, "data": {"utc": "2026-09-08T10:00:00Z"}}  # no blind_count
    return {"ok": True, "data": {"logons": [{"t": "2026-09-08T09:00:00Z",
                                             "src": "203.0.113.5", "user": "Administrator"}]}}
with mock.patch.object(patient_zero.lib, "ask", side_effect=ask_no_blind):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "blind-unknown", f"missing blind_count -> blind-unknown (got {r['termination']})")
ok(r["patient_zero"] is None, "no patient-zero claim through unknown sightedness")
ok(r["confidence"] == "low", "confidence low")

# 5b. attest transport failure -> attest-unavailable
def ask_dead(row, skill, **kw):
    if skill == "attest":
        return {"ok": False, "error": "unreachable"}
    return {"ok": True, "data": {"logons": []}}
with mock.patch.object(patient_zero.lib, "ask", side_effect=ask_dead):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "attest-unavailable", f"dead attest -> attest-unavailable (got {r['termination']})")
ok(r["patient_zero"] is None, "no patient-zero claim through a dead attest")

# 5c. a properly sighted box still walks to origin
def ask_sighted(row, skill, **kw):
    if skill == "attest":
        return {"ok": True, "data": {"utc": "2026-09-08T10:00:00Z", "blind_count": 0}}
    if row["id"] == "ws2":
        return {"ok": True, "data": {"logons": [{"t": "2026-09-08T09:00:00Z",
                                                 "src": "10.0.0.1", "user": "Administrator"}]}}
    return {"ok": True, "data": {"logons": [{"t": "2026-09-08T08:00:00Z",
                                             "src": "203.0.113.5", "user": "Administrator"}]}}
with mock.patch.object(patient_zero.lib, "ask", side_effect=ask_sighted):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "origin", f"sighted walk still reaches origin (got {r['termination']})")
ok(r["confidence"] == "high", "sighted origin keeps high confidence")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — rev20 honesty suite: ALL TESTS PASSED")
