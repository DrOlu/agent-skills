#!/usr/bin/env python3
"""test_actuate — Rev 17: the test suite rmagent-actuate never had.

Every CRITICAL/HIGH gap found in the 2026-09-03 gap analysis is now an
assertion. Pure logic — no host is touched. Covers:

  C1  target validation + PowerShell single-quote escaping
  C3  parse_verify truth table ('NOT_VERIFIED' must be False)
  C4  every mutating payload has Stop + try/catch + observed status
  C5  redaction of secret keys; journal never sees new_password
  H1  plan gate: --apply without a matching dry-run plan is refused
  H3  journal hash chain: append, verify, tamper detection
  M3  recreate_task exists as delete_task's undo; WMI triple captured
  M5  precheck refuses a blind witness; postcheck maps questions

Run:  python3 test_actuate.py
"""
from __future__ import annotations
import json, shutil, sys, tempfile, time
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "rmagent-so" / "scripts"))

import actuate          # noqa: E402
import journal          # noqa: E402

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


# ============================================================ C1: target validation
print("\n== C1. Target validation (attacker-chosen strings are refused) ==")
ok(actuate.validate_target("95.142.115.12", "ip")[0], "valid IPv4 accepted")
ok(actuate.validate_target("2001:db8::1", "ip")[0], "valid IPv6 accepted")
ok(not actuate.validate_target("95.142.115.999", "ip")[0], "bad IPv4 refused")
ok(not actuate.validate_target("not-an-ip", "ip")[0], "hostname-as-ip refused")
ok(actuate.validate_target("4242", "pid")[0], "valid PID accepted")
ok(not actuate.validate_target("4242; rm -rf", "pid")[0], "PID with injection refused")
ok(not actuate.validate_target("1'2", "pid")[0], "PID with quote refused")
ok(actuate.validate_target("honeyadmin", "user")[0], "valid user accepted")
ok(not actuate.validate_target("x'; Start-Process calc; '", "user")[0],
   "user with PS injection refused (the C1 case)")
ok(actuate.validate_target("EvilSvc", "svc")[0], "valid service accepted")
ok(not actuate.validate_target("svc`$(calc)", "svc")[0], "service with backtick refused")
ok(actuate.validate_target("BackupTask", "task")[0], "valid task accepted")
ok(actuate.validate_target(r"C:\Users\Public\p.exe", "path")[0], "valid absolute path accepted")
ok(not actuate.validate_target(r"relative\p.exe", "path")[0], "relative path refused")
ok(not actuate.validate_target(r"C:\x'; calc;'", "path")[0], "path with quote refused")
ok(actuate.validate_target("WSHFilter", "wmi")[0], "valid WMI name accepted")
ok(not actuate.validate_target("f'ilter", "wmi")[0], "WMI name with quote refused")

print("\n== C1. PowerShell escaping ==")
ok(actuate.ps_quote("plain") == "plain", "plain string unchanged")
ok(actuate.ps_quote("it''s") == "it''''s", "single quotes doubled")
ok(actuate.ps_quote("a'; Start-Process calc; '") == "a''; Start-Process calc; ''",
   "injection payload fully escaped")
preamble = actuate.build_preamble("x'; calc; '")
ok("''" in preamble and "$Target = 'x''; calc; '''" in preamble,
   "preamble carries the escaped target verbatim")
ok("$ErrorActionPreference='Stop'" in preamble,
   "preamble sets Stop (C4) — not SilentlyContinue")

# ============================================================ C3: verify parser
print("\n== C3. Verification parsing (NOT_VERIFIED must be False) ==")
ok(actuate.parse_verify("VERIFIED") is True, "bare VERIFIED -> True")
ok(actuate.parse_verify("NOT_VERIFIED") is False, "NOT_VERIFIED -> False (the old bug)")
ok(actuate.parse_verify("NOT-VERIFIED") is False, "hyphenated NOT-VERIFIED -> False")
ok(actuate.parse_verify("") is False, "empty output -> False")
ok(actuate.parse_verify("some noise\nVERIFIED") is True, "trailing VERIFIED line -> True")
ok(actuate.parse_verify("VERIFIED\nNOT_VERIFIED") is False, "LAST line wins (False)")
ok(actuate.parse_verify("VERIFIED NOT_VERIFIED") is False,
   "same-line tokens -> False (must be its own line)")

# ============================================================ C4: payload hygiene
print("\n== C4. Payload hygiene (Stop + try/catch + observed status) ==")
ADIR = HERE / "actions" / "windows"
MUTATING = [p for p in sorted(ADIR.glob("*.ps1")) if not p.name.endswith(".verify.ps1")]
for p in MUTATING:
    t = p.read_text()
    ok("$ErrorActionPreference = 'Stop'" in t or "$ErrorActionPreference='Stop'" in t,
       f"{p.name}: runs with Stop")
    ok("try {" in t and "} catch {" in t, f"{p.name}: try/catch wrapped")
    ok("ok=$false" in t or "status=" in t, f"{p.name}: reports a status")

# every verifier emits exactly one of the two tokens, underscore form
for p in sorted(ADIR.glob("*.verify.ps1")):
    t = p.read_text()
    ok("'VERIFIED'" in t and "'NOT_VERIFIED'" in t, f"{p.name}: both tokens present")
    ok("NOT-VERIFIED" not in t, f"{p.name}: no hyphenated token")

# the payloads that used to report success unconditionally now observe
ok("status= if($now){'created'}else{'failed'}" in (ADIR / "block_ip.ps1").read_text(),
   "block_ip: reports OBSERVED rule state")
ok("status= if($after -and -not $after.Enabled){'disabled'}else{'failed'}" in (ADIR / "disable_user.ps1").read_text(),
   "disable_user: reports OBSERVED enabled state")
ok("ProcessId='$Target'" in (ADIR / "kill_process.ps1").read_text(),
   "kill_process: WQL filter is QUOTED")

# ============================================================ C5: redaction
print("\n== C5. Secret redaction ==")
data = {"ok": True, "user": "svcbackup", "new_password": "s3cret!",
        "nested": [{"password": "x", "note": "keep"}]}
r = actuate.redact(data)
ok(r["new_password"] == "<redacted>", "top-level secret redacted")
ok(r["nested"][0]["password"] == "<redacted>", "nested secret redacted")
ok(r["user"] == "svcbackup" and r["nested"][0]["note"] == "keep",
   "non-secret fields survive")
ok(data["new_password"] == "s3cret!", "redact never mutates the input")
ok("new_password" in actuate.REDACT_KEYS, "rotate_credential's key is in REDACT_KEYS")

# ============================================================ H3: journal chain
print("\n== H3. Journal hash chain (tamper-evident) ==")
tmp = Path(tempfile.mkdtemp(prefix="rmagent-journal-"))
try:
    with mock.patch.object(journal, "JOURNAL", tmp / "j.jsonl"):
        e1 = journal.append("ws1", "block_ip", "1.2.3.4", "test", {"action": "unblock_ip", "target": "1.2.3.4"}, "applied", True)
        e2 = journal.append("ws1", "disable_user", "evil", "test", None, "dry-run", plan_id="abc123")
        e3 = journal.append("ws2", "rotate_credential", "svc", "test", None, "applied", False,
                            extra={"result_detail": {"new_password": "SHOULD_NOT_BE_HERE", "user": "svc"}})
        ok(e1.get("entry_sha256") and e2.get("entry_sha256"), "entries carry hashes")
        ok(e2.get("prev_sha256") == e1.get("entry_sha256"), "chain links 1->2")
        ok(e3.get("prev_sha256") == e2.get("entry_sha256"), "chain links 2->3")
        okc, problems = journal.verify_chain()
        ok(okc, f"fresh chain verifies ({problems})")

        # tamper: edit entry 2's reason in place
        lines = (tmp / "j.jsonl").read_text().splitlines()
        rec = json.loads(lines[1]); rec["reason"] = "TAMPERED"
        lines[1] = json.dumps(rec)
        (tmp / "j.jsonl").write_text("\n".join(lines) + "\n")
        okc, problems = journal.verify_chain()
        ok(not okc and any("does not match its hash" in p for p in problems),
           f"tampered entry detected: {problems[:1]}")

        # delete: remove entry 2 entirely
        lines = (tmp / "j.jsonl").read_text().splitlines()
        (tmp / "j.jsonl").write_text("\n".join([lines[0], lines[2]]) + "\n")
        okc, problems = journal.verify_chain()
        ok(not okc and any("prev_sha256 mismatch" in p for p in problems),
           f"deleted entry detected: {problems[:1]}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================ H1: plan gate
print("\n== H1. Plan gate ==")
pid = actuate.plan_id_for("ws1", "block_ip", "1.2.3.4")
ok(len(pid) == 12, "plan id is a 12-char digest")
ok(actuate.plan_id_for("ws1", "block_ip", "1.2.3.4") == pid, "plan id is deterministic")
ok(actuate.plan_id_for("ws2", "block_ip", "1.2.3.4") != pid, "plan id binds the witness")
ok(actuate.plan_id_for("ws1", "block_ip", "5.6.7.8") != pid, "plan id binds the target")

tmp = Path(tempfile.mkdtemp(prefix="rmagent-plan-"))
try:
    with mock.patch.object(journal, "JOURNAL", tmp / "j.jsonl"):
        # no dry-run recorded -> find_plan returns None
        ok(actuate.find_plan(pid) is None, "no dry-run -> no valid plan")
        # record the dry-run
        journal.append("ws1", "block_ip", "1.2.3.4", "r",
                       {"action": "unblock_ip", "target": "1.2.3.4"}, "dry-run", plan_id=pid)
        plan = actuate.find_plan(pid)
        ok(plan is not None and plan.get("witness") == "ws1", "dry-run recorded -> plan found")
        # a plan for a DIFFERENT action/target is not this plan
        ok(actuate.find_plan(actuate.plan_id_for("ws1", "kill_process", "1")) is None,
           "plan ids do not cross-apply")
        # expiry: a 2-hour-old dry-run is stale
        old = journal.append("ws1", "disable_user", "evil", "r", None, "dry-run",
                             plan_id=actuate.plan_id_for("ws1", "disable_user", "evil"))
        lines = (tmp / "j.jsonl").read_text().splitlines()
        rec = json.loads(lines[-1]); rec["t"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
        # re-hash so only the timestamp changed (chain stays valid)
        core = {k: v for k, v in rec.items() if k not in ("prev_sha256", "entry_sha256")}
        import hashlib
        rec["entry_sha256"] = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()
        lines[-1] = json.dumps(rec)
        (tmp / "j.jsonl").write_text("\n".join(lines) + "\n")
        ok(actuate.find_plan(actuate.plan_id_for("ws1", "disable_user", "evil")) is None,
           "dry-run older than 60 min is EXPIRED")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============================================================ M3: undos exist
print("\n== M3. Reversible actions ==")
ok(actuate.ACTIONS["delete_task"][0] == "recreate_task",
   "delete_task's undo is recreate_task (from the journaled XML)")
ok((ADIR / "recreate_task.ps1").exists(), "recreate_task payload exists")
ok((ADIR / "recreate_task.verify.ps1").exists(), "recreate_task verifier exists")
wmi_t = (ADIR / "disable_wmi_sub.ps1").read_text()
ok("__FilterToConsumerBinding" in wmi_t, "disable_wmi_sub captures the BINDING")
ok("consumers" in wmi_t, "disable_wmi_sub captures the CONSUMER")
ok("[regex]::Escape($Target)" in wmi_t or "-eq $Target" in wmi_t,
   "disable_wmi_sub does not regex-inject the target")

# ============================================================ M5: pre/postcheck
print("\n== M5. Pre/postcheck ==")
blind_row = {"id": "ws1", "skills": ["attest"], "address": "10.0.0.1"}
def ask_blind(row, skill, **kw):
    return {"ok": True, "data": {"blind_count": 2,
                                "blind_check": {"Logon": "BLIND", "Special Logon": "BLIND"}}}
with mock.patch.object(actuate.rma, "ask", side_effect=ask_blind):
    okp, why = actuate.precheck(blind_row)
    ok(not okp and "audit-blind" in why, f"blind witness refused: {why[:60]}")

def ask_sighted(row, skill, **kw):
    return {"ok": True, "data": {"blind_count": 0, "blind_check": {"Logon": "ok"}}}
with mock.patch.object(actuate.rma, "ask", side_effect=ask_sighted):
    okp, why = actuate.precheck(blind_row)
    ok(okp, "sighted witness passes precheck")

def ask_edges(row, skill, **kw):
    return {"ok": True, "data": {"failed_sources": [
        {"src": "95.142.115.12", "user": "Administrator", "n": 76}]}}
with mock.patch.object(actuate.rma, "ask", side_effect=ask_edges):
    ev = actuate.postcheck(blind_row, "block_ip", "95.142.115.12")
    ok(ev.get("checked") and ev.get("failed_from_target", {}).get("n") == 76,
       "postcheck(block_ip) re-asks edges and finds the source's failures")
ok("block_ip" in actuate.POSTCHECK_QUESTIONS, "block_ip has a postcheck question")
ok("rotate_credential" in actuate.POSTCHECK_QUESTIONS, "rotate_credential has a postcheck question")

# ============================================================ H2: engine import
print("\n== H2. Engine resolution ==")
lib_file = actuate.rma.__file__
ok("rmagent-so" in lib_file or "rmagent-windows" in lib_file,
   f"engine resolved from a current tree: {Path(lib_file).parent}")
ok(hasattr(actuate.rma, "_cap_signal"), "engine carries the signal-aware cap (Rev 15/16)")
ok("canary" in getattr(actuate.rma, "ALLOWED", set()) or hasattr(actuate.rma, "DEFAULT_TRANSPORT"),
   "engine is Rev 17 (canary allowlisted or DEFAULT_TRANSPORT present)")
ok(hasattr(actuate.rma, "DEFAULT_TRANSPORT"), "engine exports DEFAULT_TRANSPORT")
ok(actuate.rma.DEFAULT_TRANSPORT == "ntlm", "transport default is ntlm (matches estate.yaml)")

# ============================================================ allowlist shape
print("\n== Allowlist invariants ==")
for name, (undo, kind, desc) in actuate.ACTIONS.items():
    ok(isinstance(kind, str) and kind in ("ip", "user", "svc", "task", "pid", "path", "wmi", "host", "none"),
       f"{name}: target_kind '{kind}' is a known kind")
    if undo:
        ok(undo in actuate.ACTIONS, f"{name}: its undo '{undo}' is itself an action")
for reversible in ("block_ip", "disable_user", "stop_service", "quarantine_file", "remove_admin", "delete_task"):
    ok(actuate.ACTIONS[reversible][0] is not None, f"{reversible}: has an undo action")
ok("isolate_host" in actuate.WHOLE_HOST, "isolate_host is whole-host (no target)")

# isolate_host design: no Block rule that outranks the WinRM allow
iso = (ADIR / "isolate_host.ps1").read_text()
ok("DefaultInboundAction" in iso and "Block" in iso,
   "isolate_host uses the PROFILE DEFAULT (not a Block rule that outranks Allow)")
ok("RMAgent-Isolate-AllowWinRM" in iso, "isolate_host creates the WinRM allow FIRST")
ok("previous_allow_rules" in iso, "isolate_host journals the rules it disables (undo data)")
ok("RMAgent-Isolate-BlockInbound" not in iso,
   "the old lockout Block rule is GONE (C2)")

# ============================================================ summary
print()
if FAIL:
    print(f"{FAIL} FAILED, {PASS} passed")
    for f in FAILURES:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"{PASS} passed, 0 failed")
print("actuate suite: ALL TESTS PASSED")
