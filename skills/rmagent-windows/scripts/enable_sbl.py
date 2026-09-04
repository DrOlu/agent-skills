#!/usr/bin/env python3
"""enable_sbl — turn ON PowerShell Script-Block Logging (4104) on the estate.

MOP-level PERSISTENT change (registry policy), same discipline as autologger:
dry-run by default, --apply to change, verified after, undo documented.

WHY: Rev 17's blind_check found ScriptBlock Logging OFF on both witnesses —
pslogs (the 4104 question, "the ACTUAL CODE being executed") has been
structurally blind since the estate was built. The observatory flagged it;
this closes it.

WHAT it writes (the standard non-GPO way):
  HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\PowerShell\\ScriptBlockLogging
    EnableScriptBlockLogging = 1  (DWORD)

New PowerShell processes pick the policy up immediately — and every WinRM
knock IS a fresh process, so the next pslogs ask sees 4104 events.

UNDO:  python3 enable_sbl.py --apply --off    (sets the value back to 0;
the key is left in place so the policy path stays explicit)

Usage:
  python3 enable_sbl.py --inventory estate.yaml                 # status + plan
  python3 enable_sbl.py --inventory estate.yaml --apply         # turn ON
  python3 enable_sbl.py --inventory estate.yaml --apply --off   # undo
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

REG_KEY = r"HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging"
MARKER = "RMAgent-SBL-VERIFY"


def run_ps(row: dict, script: str) -> dict:
    import winrm
    creds = lib.creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    s = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                      transport=row.get("transport") or lib.DEFAULT_TRANSPORT)
    r = s.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else r.std_out
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else r.std_err
    return {"ok": r.status_code == 0, "stdout": (out or "").strip(),
            "stderr": (err or "").strip()[:300]}


def status_ps() -> str:
    return f"""
$k = '{REG_KEY}'
$v = $null
try {{ $v = (Get-ItemProperty $k -EA Stop).EnableScriptBlockLogging }} catch {{ }}
"current=$v"
"""


def apply_ps(on: bool) -> str:
    val = 1 if on else 0
    return f"""
$k = '{REG_KEY}'
New-Item -Path $k -Force | Out-Null
New-ItemProperty -Path $k -Name EnableScriptBlockLogging -Value {val} -PropertyType DWord -Force | Out-Null
$now = (Get-ItemProperty $k).EnableScriptBlockLogging
"set=$now"
"""


def marker_ps() -> str:
    # a distinctive script block: after SBL is on, this MUST appear in 4104
    return f"Write-Output '{MARKER}'\n"


def main():
    ap = argparse.ArgumentParser(description="enable PowerShell Script-Block Logging (MOP)")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--apply", action="store_true", help="make the change (default is status+plan)")
    ap.add_argument("--off", action="store_true", help="with --apply: turn it back OFF (undo)")
    args = ap.parse_args()

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    turning_on = not args.off

    # ---------- plan / status ----------
    print(f"[plan] {'ENABLE' if turning_on else 'DISABLE'} Script-Block Logging on {len(rows)} witness(es)")
    print(f"  registry: {REG_KEY}")
    print(f"  value   : EnableScriptBlockLogging = {1 if turning_on else 0} (DWORD)")
    print(f"  effect  : PowerShell 4104 events land in Microsoft-Windows-PowerShell/Operational")
    print(f"            -> pslogs (the script-block question) stops being blind")
    print(f"  undo    : enable_sbl.py --inventory {args.inventory} --apply --off")
    print()

    for row in rows:
        wid = row.get("id")
        st = run_ps(row, status_ps())
        cur = "unknown"
        for line in st.get("stdout", "").splitlines():
            if line.startswith("current="):
                cur = line.split("=", 1)[1] or "not-set"
        print(f"[{wid}] current EnableScriptBlockLogging = {cur}")

    if not args.apply:
        print("\n(dry-run — nothing changed. re-run with --apply to make the change.)")
        return

    # ---------- apply ----------
    print()
    for row in rows:
        wid = row.get("id")
        res = run_ps(row, apply_ps(turning_on))
        got = ""
        for line in res.get("stdout", "").splitlines():
            if line.startswith("set="):
                got = line.split("=", 1)[1]
        want = "1" if turning_on else "0"
        print(f"[{wid}] registry set -> {got} ({'OK' if got == want else 'FAIL'})")

    # ---------- verify: the observatory confirms its own cure ----------
    print()
    for row in rows:
        wid = row.get("id")
        # 1. the blind_check must now say ok
        att = lib.ask(row, "attest", since_hours=1.0, limit=5)
        bc = (att.get("data") or {}).get("blind_check") or {}
        sbl = bc.get("ScriptBlock Logging")
        print(f"[{wid}] attest blind_check['ScriptBlock Logging'] = {sbl}")

        # 2. end-to-end: generate a distinctive script block, then read it back
        if turning_on:
            run_ps(row, marker_ps())
            pl = lib.ask(row, "pslogs", since_hours=1.0, limit=50)
            blocks = (pl.get("data") or {}).get("blocks") or []
            hit = any(MARKER in (b.get("msg") or "") for b in blocks)
            print(f"[{wid}] pslogs: {len(blocks)} block(s), marker found = {hit}")
            if not hit:
                print(f"[{wid}]   (4104 may take a moment; re-run pslogs shortly)")

    print()
    print("done." if turning_on else "undone.")


if __name__ == "__main__":
    main()
