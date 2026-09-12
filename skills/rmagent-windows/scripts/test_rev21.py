#!/usr/bin/env python3
"""test_rev21 — AD/DC questions + SSH witness door.

Pure logic + a safe SSH attempt (holes on failure, never crashes).
"""
from __future__ import annotations
import base64
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent / "rmagent-core" / "scripts"

spec = importlib.util.spec_from_file_location("eng", CORE / "engine.py")
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)
specg = importlib.util.spec_from_file_location("gr", CORE / "grains.py")
gr = importlib.util.module_from_spec(specg)
specg.loader.exec_module(gr)

PASS = FAIL = 0
FAILS = []


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {label}")
    else:
        FAIL += 1
        FAILS.append(label)
        print(f"  FAIL {label}")


print("== grain: AD questions are identity grain ==")
ID = gr.allowed_for("rmagent-so")
for q in ("krb", "dcsync", "dirchange"):
    ok(q in ID, f"{q} in IDENTITY grain")
ok("krb" not in gr.allowed_for("rmagent-at"), "krb is foreign on the app skill")
ok(ID == gr.allowed_for("rmagent-windows"), "so and windows share the grain")

print("== payloads exist + fit budget ==")
Q = HERE / "questions" / "windows"
for q in ("krb", "dcsync", "dirchange"):
    p = Q / f"{q}.ps1"
    ok(p.exists(), f"{q}.ps1 exists")
    body = "\n".join(l for l in p.read_text().splitlines()
                     if l.strip() and not l.strip().startswith("#"))
    enc = base64.b64encode(body.encode("utf-16-le")).decode()
    n = len("powershell -encodedcommand ") + len(enc)
    ok(n + 900 <= 8191, f"{q}.ps1 body {n} + preamble fits 8191")

print("== SSH door ==")
ok(hasattr(eng, "_ask_ssh"), "_ask_ssh exists")
ok(hasattr(eng, "_sh_preamble"), "_sh_preamble exists")
src = (CORE / "engine.py").read_text()
ok('door == "ssh"' in src, "ask() handles door == ssh")
ok('"linux" / f"{skill}.sh"' in src, "ssh door reads questions/linux/*.sh")
i_guard = src.find("if not use_ssh and winrm is None")
i_ssh = src.find("if use_ssh:")
ok(0 < i_guard < i_ssh, "pywinrm guard is after the door split (ssh works without pywinrm)")

print("== ssh door returns a hole, never a crash ==")
eng.ALLOWED = set(ID)
row = {"id": "lin1", "os": "linux", "address": "127.0.0.1", "door": "ssh",
       "skills": ["attest"], "track": ["root"]}
r = eng.ask(row, "attest")
ok(isinstance(r, dict) and "ok" in r, "ssh ask() returns a structured result")
ok(r.get("ok") or r.get("hole"), "ssh failure is a hole, not an exception")

print("== _sh_preamble shape ==")
pre = eng._sh_preamble({"track": ["root", "ops"]}, 2.0, 50)
ok("export TRACK='root,ops'" in pre, "preamble exports TRACK")
ok("export SINCE_HOURS=2.0" in pre and "export LIMIT=50" in pre, "preamble exports window+limit")

print("== krb payload semantics ==")
k = (Q / "krb.ps1").read_text()
for eid in ("4768", "4769", "4771", "4776"):
    ok(eid in k, f"krb covers {eid}")
ok("0x17" in k, "krb flags RC4 etype 0x17 (roastable)")
ok("PreAuthType" in k, "krb checks pre-auth (AS-REP roast)")

print("== dcsync payload semantics ==")
d = (Q / "dcsync.ps1").read_text()
ok("1131f6aa" in d and "1131f6ad" in d, "dcsync carries replication-rights GUIDs")
ok("4662" in d, "dcsync reads 4662")
ok("SubjectUserName" in d, "dcsync attributes the principal")

print("== dirchange payload semantics ==")
dc = (Q / "dirchange.ps1").read_text()
ok("Domain Admins" in dc and "Enterprise Admins" in dc, "dirchange tracks privileged groups")
ok("1102" in dc, "dirchange catches audit policy cleared")

print("== attest reports domain_role + DC blind check ==")
at = (Q / "attest.ps1").read_text()
ok("domain_role" in at, "attest reports domain_role")
ok("DC-Audit" in at, "attest adds DC-Audit blind check when role=dc")

print()
if FAIL:
    print(f"{FAIL} FAILED, {PASS} passed")
    for f in FAILS:
        print("  x", f)
    sys.exit(1)
print(f"{PASS} passed, 0 failed — rev21: ALL TESTS PASSED")
