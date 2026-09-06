#!/usr/bin/env python3
"""Verify every question payload fits WinRM's ~8191-char command budget.

The preamble + payload get UTF-16LE base64-encoded by pywinrm (~2.7x growth).
A payload over that budget fails with 'The command line is too long.' —
this is the Rev 8 lesson, now enforced as a test rather than a memory.

Rev 16 FIX: the budget is the COMMAND LINE, not the encoded blob — pywinrm
prepends 'powershell -encodedcommand ' (27 chars) to build it. The old test
measured only the blob, so edges at 8176/8191 passed the test and then
failed LIVE with 8203. The wrapper is now included.

Rev 17 FIX (found live on WS1): two more lessons.
  1. The test's fixed preamble was SMALLER than the real one. The engine
     injects the witness's canary list into the preamble — a witness with
     two canaries sends 26 more chars than the test modeled, and edges
     passed the test at 8187 then failed live. The test now builds the
     WORST-CASE preamble: the longest canary list in the inventory (or a
     3-canary default when no inventory is present).
  2. cmd.exe wraps the command server-side and adds overhead the model
     cannot see. A payload that measures at 8187/8191 is not safely under
     budget. The test now enforces a SAFETY MARGIN: measured + MARGIN must
     be <= 8191, so a 'pass' means real headroom, not a rounding hair.
"""
import base64
import sys
from pathlib import Path

QDIR = Path(__file__).resolve().parent / "questions" / "windows"
BUDGET = 8191
MARGIN = 200          # cmd.exe wrapper overhead + model error (Rev 17, live lesson)
WRAPPER = "powershell -encodedcommand "

# ---------------------------------------------------------------- worst-case preamble
# The engine's _preamble() injects $Track, $SinceHours, $Limit, $CanaryList.
# Worst realistic case: 2 tracked principals, a float window, limit 50, and
# the longest canary list found in the estate inventory (default 3 canaries).
def worst_canary_list() -> list[str]:
    try:
        import yaml
        inv_path = Path.home() / "estate.yaml"
        if inv_path.exists():
            inv = yaml.safe_load(inv_path.read_text())
            lists = [w.get("canaries") or [] for w in (inv.get("witnesses") or [])]
            if lists:
                return max(lists, key=len)
    except Exception:
        pass
    return ["canary-one", "canary-two", "canary-three"]


canaries = worst_canary_list()
track = ["Administrator", "SYSTEM"]
track_items = "','".join(track)
c_items = "','".join(canaries)
PREAMBLE = ("$ErrorActionPreference='SilentlyContinue'\n"
            f"$Track = @('{track_items}')\n"
            "$SinceHours = 2.0\n$Limit = 50\n"
            f"$CanaryList = @('{c_items}')\n")

print(f"worst-case preamble: {len(PREAMBLE)} chars "
      f"({len(track)} track, {len(canaries)} canaries: {canaries})")
print(f"budget: {BUDGET} with a {MARGIN}-char safety margin "
      f"(effective limit {BUDGET - MARGIN})\n")


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
    n = len(WRAPPER) + len(enc)
    status = "OK " if n + MARGIN <= BUDGET else "OVER"
    if n + MARGIN > BUDGET:
        fails += 1
    print(f"  {status} {p.name:22s} {n:5d} +{MARGIN} margin / {BUDGET} chars "
          f"({100 * n // BUDGET}%, headroom {BUDGET - MARGIN - n})")

print()
if fails:
    print(f"{fails} payload(s) OVER BUDGET (or inside the safety margin)")
    sys.exit(1)
print(f"all payloads fit the WinRM budget with {MARGIN} chars of headroom")
