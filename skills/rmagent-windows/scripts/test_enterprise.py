#!/usr/bin/env python3
"""Rev 15 enterprise test suite — pure-logic tests for the new capabilities.

Covers, WITHOUT touching a real host:
  1. signal-aware cap (triage instead of drop)
  2. canary preamble injection ($CanaryList)
  3. patient-zero walk termination honesty (origin vs retention-boundary
     vs blind-witness vs no-signal vs cycle)
  4. drift canary tripwire finding
  5. correlate triage ranking + recommended actions
  6. actuate allowlist: new actions present, whole-host target rules

Run:  python3 test_enterprise.py
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib          # rmagent-so engine
import drift        # rmagent-so drift
import correlate    # rmagent-so correlate
import patient_zero # rmagent-so patient-zero walk

PASS = 0
FAIL = 0
FAILURES = []


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL  {label}")


# ============================================================ 1. signal-aware cap
print("\n== 1. Signal-aware cap: triage instead of drop ==")

row = {"id": "ws1", "skills": ["edges"], "address": "10.0.0.1"}

# (a) under budget → untouched
small = {"ok": True, "data": {"logons": [{"user": "a"}]}}
res = lib._cap_signal(dict(small), row, "edges")
ok(res.get("ok") and not res.get("capped"), "under-budget answer passes through untouched")

# (b) over budget WITH critical rows → trimmed, critical survives, still ok
# 400 rows × ~110 bytes ≈ 44 KB — genuinely over the 32 KB cap.
noisy = [{"user": f"noise-user-{i}", "src": "10.0.0.9", "t": "2026-08-30T00:00:00Z",
          "lid": f"0x{i:x}", "auth": "NtLmSsp", "type": "3"} for i in range(400)]
critical = [{"user": "Administrator", "src": "95.142.115.12", "t": "2026-08-30T00:00:00Z",
              "eid": "4648"}]
data = {"logons": noisy + critical}
big = {"ok": True, "data": data}
size_before = len(json.dumps(data).encode())
res = lib._cap_signal(dict(big), row, "edges")
ok(size_before > lib.MAX_PULL_BYTES, f"fixture is genuinely over budget ({size_before} > {lib.MAX_PULL_BYTES})")
ok(res.get("ok"), "over-budget answer with critical rows is NOT dropped to a hole")
ok(res.get("capped") is True, "answer is marked capped")
survived = res["data"]["logons"]
ok(any(l.get("eid") == "4648" for l in survived), "the critical 4648 row SURVIVES the trim")
ok(len(survived) < len(noisy) + 1, f"noise was shed ({len(survived)} rows kept)")
ok(len(json.dumps(res["data"]).encode()) <= lib.MAX_PULL_BYTES, "result is under the cap — still no lake")

# (c) over budget with NOTHING critical → falls back to a hole (honest)
allnoise = {"logons": [{"user": f"n{i}", "src": "10.0.0.9", "t": "2026-08-30T00:00:00Z"} for i in range(400)]}
res = lib._cap_signal({"ok": True, "data": allnoise}, row, "edges")
# noise-only may still fit after shedding (all rows are signal-1) — either way it must not lie
if res.get("ok"):
    ok(len(json.dumps(res["data"]).encode()) <= lib.MAX_PULL_BYTES, "noise-only result is under the cap")
else:
    ok(bool(res.get("hole")), "untrimmable answer becomes a hole (honest, not silent)")

# (d) failed result keeps its hole
res = lib._cap_signal({"ok": False, "error": "unreachable"}, row, "edges")
ok(not res.get("ok") and res.get("hole"), "failed ask still carries a hole")


# ============================================================ 2. canary preamble
print("\n== 2. Canary preamble injection ==")

p = lib._preamble({"id": "ws1", "canaries": ["honeyadmin", "svcbackup2"]}, 2.0, 50, "canary")
ok("$CanaryList = @('honeyadmin','svcbackup2')" in p, "canary names injected as a proper PS array")
p2 = lib._preamble({"id": "ws1"}, 2.0, 50, "canary")
ok("$CanaryList = @('')" in p2, "absent canaries → empty array (payload falls back to heuristics)")
p3 = lib._preamble({"id": "ws1", "canaries": "not-a-list"}, 2.0, 50, "canary")
ok("$CanaryList = @('')" in p3, "non-list canaries value is tolerated (no crash)")
p4 = lib._preamble({"id": "ws1", "canaries": ["o'neil"]}, 2.0, 50, "canary")
ok("''" in p4, "single-quote in a canary name is escaped")
ok("canary" in lib.ALLOWED, "canary is in the allowlist")
ok((lib.QDIR / "windows" / "canary.ps1").exists(), "canary payload exists")


# ============================================================ 3. patient-zero walk
print("\n== 3. Patient-zero walk: honest termination ==")

# inventory: ws2 <- ws1 <- EXTERNAL
INV = {"witnesses": [
    {"id": "ws1", "address": "10.0.0.1", "skills": ["attest", "edges"],
     "track": ["Administrator", "SYSTEM"]},
    {"id": "ws2", "address": "10.0.0.2", "skills": ["attest", "edges"],
     "track": ["Administrator", "SYSTEM"]},
]}

def fake_ask(row, skill, **kw):
    """Deterministic fake answers for the walk."""
    wid = row["id"]
    if skill == "attest":
        # log retains a FULL month of history — well before the window we walk
        return {"ok": True, "data": {"blind_count": 0, "blind_check": {},
                                    "oldest_security_event": "2026-08-01T00:00:00Z"}}
    if skill == "edges":
        if wid == "ws2":
            # oldest inbound logon came from ws1
            return {"ok": True, "data": {"logons": [
                {"t": "2026-08-30T10:00:00Z", "user": "Administrator", "type": "3",
                 "src": "10.0.0.1", "lid": "0xabc", "auth": "NtLmSsp"},
                {"t": "2026-08-30T11:00:00Z", "user": "Administrator", "type": "3",
                 "src": "10.0.0.1", "lid": "0xdef", "auth": "NtLmSsp"},
            ]}}
        if wid == "ws1":
            # oldest inbound logon came from OUTSIDE
            return {"ok": True, "data": {"logons": [
                {"t": "2026-08-30T09:00:00Z", "user": "Administrator", "type": "3",
                 "src": "95.142.115.12", "lid": "0x111", "auth": "NtLmSsp"},
            ]}}
    return {"ok": False, "error": "nope"}

with mock.patch.object(lib, "ask", side_effect=fake_ask):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "origin", f"clean walk terminates at ORIGIN (got {r['termination']})")
ok(r["patient_zero"] == "ws1", f"patient zero is ws1 (got {r.get('patient_zero')})")
ok(r["confidence"] == "high", "origin termination → high confidence")
ok(r["hop_count"] == 2, f"two hops walked (got {r['hop_count']})")
ok(r["hops"][0]["src_is_estate"] is True, "hop 0 (ws2) source IS in the estate")
ok(r["hops"][1]["src_is_estate"] is False, "hop 1 (ws1) source is EXTERNAL")

# --- retention boundary: the log's oldest event is AT the relied-on logon,
# so there is no visibility before it — older logons may have rotated away.
def ask_retention(row, skill, **kw):
    wid = row["id"]
    if skill == "attest":
        if wid == "ws1":
            # ws1's log starts exactly at the logon we relied on (09:00) —
            # anything earlier is GONE, so "external" may just mean "before
            # the log began". The walk must NOT claim an origin.
            return {"ok": True, "data": {"blind_count": 0,
                                        "oldest_security_event": "2026-08-30T09:00:00Z"}}
        return {"ok": True, "data": {"blind_count": 0,
                                     "oldest_security_event": "2026-08-01T00:00:00Z"}}
    return fake_ask(row, skill, **kw)

with mock.patch.object(lib, "ask", side_effect=ask_retention):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "retention-boundary",
   f"log edge newer than the relied-on logon → RETENTION-BOUNDARY (got {r['termination']})")
ok(r.get("patient_zero") is None, "retention boundary → patient zero NOT claimed")
ok(r["confidence"] == "low", "retention boundary → low confidence")
ok("widen" in r["note"], "retention note tells the operator what to do next")

# --- blind witness: refuse to claim an origin through it
def ask_blind(row, skill, **kw):
    if skill == "attest":
        return {"ok": True, "data": {"blind_count": 3,
                                    "blind_check": {"Logon": "BLIND"}}}
    return fake_ask(row, skill, **kw)

with mock.patch.object(lib, "ask", side_effect=ask_blind):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "blind-witness", f"blind witness → BLIND-WITNESS termination (got {r['termination']})")
ok(r.get("patient_zero") is None, "blind witness → no patient-zero claim")
ok(any(h.get("blind") for h in r["hops"]), "the blind hop is recorded as blind")

# --- no signal
def ask_nosignal(row, skill, **kw):
    if skill == "attest":
        return {"ok": True, "data": {"blind_count": 0}}
    if skill == "edges":
        return {"ok": True, "data": {"logons": []}}
    return {"ok": False, "error": "?"}

with mock.patch.object(lib, "ask", side_effect=ask_nosignal):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "no-signal", f"empty edges → NO-SIGNAL (got {r['termination']})")

# --- cycle: ws2 -> ws1 -> ws2
def ask_cycle(row, skill, **kw):
    if skill == "attest":
        return {"ok": True, "data": {"blind_count": 0}}
    if skill == "edges":
        src = "10.0.0.2" if row["id"] == "ws1" else "10.0.0.1"
        return {"ok": True, "data": {"logons": [
            {"t": "2026-08-30T09:00:00Z", "user": "Administrator", "type": "3",
             "src": src, "lid": "0x111", "auth": "NtLmSsp"}]}}
    return {"ok": False, "error": "?"}

with mock.patch.object(lib, "ask", side_effect=ask_cycle):
    r = patient_zero.walk(INV, "ws2", 24.0, 50)
ok(r["termination"] == "cycle", f"mutual logons → CYCLE detected (got {r['termination']})")


# ============================================================ 4. drift canary
print("\n== 4. Drift: canary tripwire finding ==")

old_snap = {"witness": "ws1", "admins": ["Administrator"], "taken_utc": "2026-08-29T00:00:00Z"}
new_tripped = {"witness": "ws1", "admins": ["Administrator"], "taken_utc": "2026-08-30T00:00:00Z",
               "canary": {"armed": ["honeyadmin"], "armed_count": 1, "hit_count": 3,
                          "tripped": True, "sources": ["95.142.115.12"]}}
d = drift.diff(old_snap, new_tripped)
kinds = [f["kind"] for f in d["findings"]]
ok("canary_tripped" in kinds, "a tripped canary produces a canary_tripped finding")
ct = next(f for f in d["findings"] if f["kind"] == "canary_tripped")
ok(ct["severity"] == "critical", "canary_tripped is critical")
ok("95.142.115.12" in ct["detail"], "the source IP appears in the detail")

new_unarmed = {"witness": "ws1", "admins": ["Administrator"], "taken_utc": "2026-08-30T00:00:00Z",
               "canary": {"armed": [], "armed_count": 0, "hit_count": 0,
                          "tripped": False, "sources": []}}
d = drift.diff(old_snap, new_unarmed)
kinds = [f["kind"] for f in d["findings"]]
ok("canary_unarmed" in kinds, "an estate with no canaries gets an informational nudge")
cu = next(f for f in d["findings"] if f["kind"] == "canary_unarmed")
ok(cu["severity"] == "info", "canary_unarmed is informational, not an alarm")

new_clean = {"witness": "ws1", "admins": ["Administrator"], "taken_utc": "2026-08-30T00:00:00Z",
             "canary": {"armed": ["honeyadmin"], "armed_count": 1, "hit_count": 0,
                        "tripped": False, "sources": []}}
d = drift.diff(old_snap, new_clean)
kinds = [f["kind"] for f in d["findings"]]
ok("canary_tripped" not in kinds and "canary_unarmed" not in kinds,
   "an armed, untouched canary produces NO finding (correct — silence is success)")


# ============================================================ 5. correlate triage
print("\n== 5. Correlate: triage ranking + recommended actions ==")

ROWS = [{"id": "ws1", "address": "10.0.0.1"}, {"id": "ws2", "address": "10.0.0.2"}]
answers = {
    # a canary hit on ws1 from an external IP
    "ws1__canary": {"tripped": True, "hit_count": 2, "sources": ["95.142.115.12"]},
    # shared LogonId across both boxes
    "ws1__edges": {"logons": [{"t": "2026-08-30T10:00:00Z", "user": "Administrator",
                               "src": "10.0.0.2", "lid": "0xabc", "auth": "NtLmSsp"}],
                   "explicit_creds": [], "conns": []},
    "ws2__edges": {"logons": [{"t": "2026-08-30T10:30:00Z", "user": "Administrator",
                               "src": "10.0.0.1", "lid": "0xabc", "auth": "NtLmSsp"}],
                   "explicit_creds": [], "conns": []},
    # a lateral hop ws1 -> ws2
    "ws1__netedges": {"conns": [{"dest": "10.0.0.2", "port": "445", "user": "Administrator"}]},
}
res = correlate.correlate(answers, ROWS)
kinds = [f["kind"] for f in res["findings"]]
ok("canary_tripped" in kinds, "correlate surfaces the canary hit")
ok("shared-logonid" in kinds, "correlate still finds shared-logonid")
ok("lateral-hop" in kinds, "correlate still finds lateral-hop")
order = [f["kind"] for f in res["findings"]]
ok(order.index("canary_tripped") < order.index("shared-logonid"),
   "canary outranks shared-logonid (rank 0 < rank 1)")
ok(order.index("shared-logonid") < order.index("lateral-hop"),
   "shared-logonid outranks lateral-hop")
ct = next(f for f in res["findings"] if f["kind"] == "canary_tripped")
ok("block_ip" in ct.get("recommended_actions", []), "canary finding recommends block_ip first")
ok("triage" in res and "top" in res["triage"], "result carries a triage block")
ok(res["triage"]["top"][0] == "canary_tripped", "triage.top is led by the canary")
lh = next(f for f in res["findings"] if f["kind"] == "lateral-hop")
ok("triage_why" in lh and lh["triage_why"], "each finding carries a triage_why explanation")


# ============================================================ 6. actuate allowlist
print("\n== 6. Actuate: new actions in the allowlist ==")

ACT_DIR = Path.home() / ".agents" / "skills" / "rmagent-actuate" / "scripts"
sys.path.insert(0, str(ACT_DIR))
# actuate.py imports lib from rmagent-windows; stub what it needs
sys.path.insert(0, str(HERE))
import importlib.util
spec = importlib.util.spec_from_file_location("actuate_mod", ACT_DIR / "actuate.py")
am = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(am)
    A = am.ACTIONS
    ok("rotate_credential" in A, "rotate_credential is in the allowlist")
    ok("isolate_host" in A, "isolate_host is in the allowlist")
    ok("un_isolate_host" in A, "un_isolate_host is in the allowlist")
    ok(A["isolate_host"][0] == "un_isolate_host", "isolate_host has an undo")
    ok((ACT_DIR / "actions" / "windows" / "rotate_credential.ps1").exists(),
       "rotate_credential payload exists")
    ok((ACT_DIR / "actions" / "windows" / "isolate_host.ps1").exists(),
       "isolate_host payload exists")
    ok((ACT_DIR / "actions" / "windows" / "un_isolate_host.ps1").exists(),
       "un_isolate_host payload exists")
    ok((ACT_DIR / "actions" / "windows" / "rotate_credential.verify.ps1").exists(),
       "rotate_credential verifier exists")
    ok((ACT_DIR / "actions" / "windows" / "isolate_host.verify.ps1").exists(),
       "isolate_host verifier exists")
    ok((ACT_DIR / "actions" / "windows" / "un_isolate_host.verify.ps1").exists(),
       "un_isolate_host verifier exists")
    # every action in the allowlist must have a payload
    missing = [a for a in A if a != "snapshot"
               and not (ACT_DIR / "actions" / "windows" / f"{a}.ps1").exists()]
    ok(not missing, f"every allowlisted action has a payload (missing: {missing})")
    # every undo must itself be allowlisted
    bad_undo = [a for a, (u, *_r) in A.items() if u and u not in A]
    ok(not bad_undo, f"every undo action is itself allowlisted (bad: {bad_undo})")
except Exception as e:
    ok(False, f"actuate module loads: {e}")


# ============================================================ summary
print(f"\n{PASS} passed, {FAIL} failed")
if FAIL:
    print("FAILURES:")
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1)
print("enterprise suite: ALL TESTS PASSED")
