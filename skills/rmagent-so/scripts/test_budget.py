#!/usr/bin/env python3
"""Verify every question payload fits WinRM's ~8191-char command budget.

The preamble + payload get UTF-16LE base64-encoded by pywinrm (~2.7x growth).
A payload over that budget fails with 'The command line is too long.' —
this is the Rev 8 lesson, now enforced as a test rather than a memory.

Rev 16 FIX: the budget is the COMMAND LINE, not the encoded blob — pywinrm
prepends 'powershell -encodedcommand ' (27 chars) to build it. The old test
measured only the blob, so edges at 8176/8191 passed the test and then
failed LIVE with 8203. The wrapper is now included.
"""
import base64, sys
from pathlib import Path

QDIR = Path(__file__).resolve().parent / "questions" / "windows"
BUDGET = 8191
# pywinrm's run_ps wraps the blob in this command-line prefix
WRAPPER = "powershell -encodedcommand "

# the real preamble the engine builds (a representative one)
PREAMBLE = ("$ErrorActionPreference='SilentlyContinue'\n"
            "$Track = @('Administrator','SYSTEM')\n"
            "$SinceHours = 2.0\n$Limit = 50\n"
            "$CanaryList = @('honeyadmin','svcbackup2')\n")

def strip_payload(text: str) -> str:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(line.rstrip())
    return "\n".join(out)

fails = 0
for p in sorted(QDIR.glob("*.ps1")):
    body = strip_payload(p.read_text())
    script = PREAMBLE + body
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    # Rev 16: the budget is the COMMAND LINE pywinrm builds, which includes
    # the 'powershell -encodedcommand ' wrapper prefix.
    n = len(WRAPPER) + len(enc)
    status = "OK " if n <= BUDGET else "OVER"
    if n > BUDGET:
        fails += 1
    print(f"  {status} {p.name:22s} {n:5d} / {BUDGET} chars ({100*n//BUDGET}%)")

print()
if fails:
    print(f"{fails} payload(s) OVER BUDGET")
    sys.exit(1)
print("all payloads fit the WinRM budget")
