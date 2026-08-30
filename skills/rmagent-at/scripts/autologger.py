#!/usr/bin/env python3
"""rmagent-at autologger — enterprise-scale ETW session management.

Creates and manages AutoLogger sessions that start at BOOT and run resident
in kernel memory. The ring buffer is circular: old events are overwritten,
nothing hits disk until the pull reads it. No lake.

ENTERPRISE SCALE: the default session uses a 512 MB kernel ring buffer with
a 256 MB file cap, giving hours-to-days of retention on a busy box instead
of minutes. Buffer sizes are tunable per session.

TRANSPORT NOTE (found live on WS1/WS2, 2026-08-30): Impacket's reg.py
(C:\\Python314\\Scripts\\reg.py) SHADOWS Windows reg.exe in the WinRM PATH.
Every bare `reg add` was silently calling Impacket and failing. ALL registry
writes in this script use the absolute path C:\\Windows\\System32\\reg.exe.
Same for logman: C:\\Windows\\System32\\logman.exe.

This is a PERSISTENT CHANGE to the witness (registry + boot-time session).
It is a MOP-level action, not a Phase 0 question. Every function here is
reversible via `teardown()`.

Usage:
  python3 autologger.py --inventory estate.yaml --setup          # create sessions
  python3 autologger.py --inventory estate.yaml --status         # what's running
  python3 autologger.py --inventory estate.yaml --resize 1024    # grow buffers
  python3 autologger.py --inventory estate.yaml --teardown       # remove everything
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

# ---------------------------------------------------------------- constants

# ABSOLUTE PATHS — Impacket's reg.py shadows reg.exe in the WinRM PATH on
# this estate. Bare `reg` calls Impacket and silently fails.
REG = r"C:\Windows\System32\reg.exe"
LOGMAN = r"C:\Windows\System32\logman.exe"

REG_BASE = r"HKLM\SYSTEM\CurrentControlSet\Control\WMI\Autologger"

SESSIONS = [
    {
        "name": "RMAgent-AppTrace",
        "purpose": "application-level events (.NET EventSource, HTTP.sys, IIS)",
        "buffer_mb": 512,
        "file_cap_mb": 256,
        "providers": [
            "e13c0d23-ccbc-4e12-931b-d9cc2eedb7d1",  # .NET CLR
            "7b9a21c0-2f55-4e75-b6c1-0b0a5e1f6b6d",  # HTTP.sys
            "d9d1d5b8-2f5a-4e75-b6c1-0b0a5e1f6b6d",  # ASP.NET
        ],
    },
    {
        "name": "RMAgent-NetTrace",
        "purpose": "connection-level network (every TCP connection with PID)",
        "buffer_mb": 256,
        "file_cap_mb": 128,
        "providers": [
            "7dd42a49-5329-4832-8dfd-43d979153a88",  # Kernel-Network
        ],
    },
    {
        "name": "RMAgent-ProcTrace",
        "purpose": "process lifecycle (create/exit with full command line)",
        "buffer_mb": 128,
        "file_cap_mb": 64,
        "providers": [
            "22fb2cd6-0c7b-422b-b0c5-2e8b9918b978",  # Kernel-Process
        ],
    },
]


# ---------------------------------------------------------------- payloads

def _setup_ps(session: dict, buffer_mb: int) -> str:
    """PowerShell to create one AutoLogger session. Compact for WinRM.

    Uses ABSOLUTE reg.exe path (Impacket shadows it). Errors on the logman
    call are NOT swallowed — a failed session start must surface.
    """
    name = session["name"]
    provs = ",".join(session["providers"])
    file_cap = session["file_cap_mb"]
    return f"""
$ErrorActionPreference='Continue'
$name='{name}'
$base='{REG_BASE}\\'+$name
$REG='{REG}'
# session root — ABSOLUTE PATH (Impacket's reg.py shadows reg.exe)
& $REG add $base /v Start /t REG_DWORD /d 1 /f
& $REG add $base /v MaxFileSize /t REG_DWORD /d 0x{file_cap * 1024 * 1024:x} /f
& $REG add $base /v FileName /t REG_SZ /d "C:\\etw\\{name}.etl" /f
& $REG add $base /v LogFileMode /t REG_DWORD /d 0x1004 /f
& $REG add $base /v BufferSize /t REG_DWORD /d 1024 /f
& $REG add $base /v MinimumBuffers /t REG_DWORD /d {buffer_mb} /f
& $REG add $base /v MaximumBuffers /t REG_DWORD /d {buffer_mb * 2} /f
& $REG add $base /v FlushTimer /t REG_DWORD /d 0 /f
New-Item -ItemType Directory -Path 'C:\\etw' -Force | Out-Null
# providers
$provs = '{provs}'.Split(',')
$i = 0
foreach($p in $provs){{
  $pk = $base + '\\' + $p
  & $REG add $pk /v Enabled /t REG_DWORD /d 1 /f
  & $REG add $pk /v Level /t REG_DWORD /d 0xff /f
  & $REG add $pk /v MatchAnyKeyword /t REG_QWORD /d 0xffffffffffffffff /f
  $i++
}}
# VERIFY the registry writes actually landed (Impacket shadow check)
$verifyStart = & $REG query $base /v Start 2>&1 | Out-String
if($verifyStart -notmatch '0x1'){{
  Write-Output "REGFAIL $name Start not written"
  exit 1
}}
# Create the session ONCE with the first provider, then logman update to add
# the rest. Calling `create` repeatedly for the same name fails on the 2nd
# call ("already exists") — that is why the 3-provider AppTrace session
# ended up Status: Stop while the single-provider sessions worked.
# FOUR logman quirks found live on WS1/WS2 (2026-08-30):
#   1. -o is parsed as -outputFormat -> omit it entirely.
#   2. -p REQUIRES the GUID wrapped in braces; bare GUID = "Element not found".
#   3. -ets makes the session EPHEMERAL (invisible to logman query). Create
#      WITHOUT -ets, then `logman start <name>`.
#   4. One create per name; additional providers go in via `logman update`.
$first = $provs[0]
& '{LOGMAN}' create trace $name -p "{{$first}}" 2>&1 | Out-Null
if($LASTEXITCODE -ne 0){{
  Write-Output "LMFAIL $name logman create failed"
  exit 1
}}
# add the remaining providers via update (a no-op when there is only one)
if($provs.Count -gt 1){{
  foreach($p in $provs | Select-Object -Skip 1){{
    & '{LOGMAN}' update trace $name -p "{{$p}}" 2>&1 | Out-Null
  }}
}}
& '{LOGMAN}' start $name 2>&1 | Out-Null
# HARD VERIFY: the session must actually exist and be running
$q = & '{LOGMAN}' query $name 2>&1 | Out-String
if(($q -notmatch '(?i)Running') -or ($q -match '(?i)not found')){{
  Write-Output "LMFAIL $name session not running after start"
  exit 1
}}
Write-Output "SETUP $name buffers={buffer_mb}MB providers=$i"
""".strip()


def _status_ps() -> str:
    """Status with ABSOLUTE reg.exe path and real running check."""
    return f"""
$ErrorActionPreference='SilentlyContinue'
$REG='{REG}'
$LM='{LOGMAN}'
$out=@()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  $base='{REG_BASE}\\'+$n
  $start=(& $REG query $base /v Start 2>$null | Out-String) -replace '.*REG_DWORD\s+',''
  $buf=(& $REG query $base /v MinimumBuffers 2>$null | Out-String) -replace '.*REG_DWORD\s+',''
  $q = & $LM query $n 2>&1 | Out-String
  $running = ($q -match '(?i)Running') -and ($q -notmatch '(?i)not found')
  $out += [pscustomobject]@{{name=$n;start=$start.Trim();buffer_mb=$buf.Trim();running=$running}}
}}
$out | ConvertTo-Json -Compress
""".strip()


def _teardown_ps() -> str:
    """Teardown with ABSOLUTE paths. Persistent sessions: stop WITHOUT -ets
    (the -ets flag only applies to ephemeral sessions), then delete."""
    return f"""
$ErrorActionPreference='Continue'
$REG='{REG}'
$LM='{LOGMAN}'
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  # persistent Data Collector Set: stop + delete WITHOUT -ets
  & $LM stop $n 2>&1 | Out-Null
  & $LM delete $n 2>&1 | Out-Null
  # also try the -ets form in case an ephemeral one is left over
  & $LM stop $n -ets 2>&1 | Out-Null
  & $LM delete $n -ets 2>&1 | Out-Null
  & $REG delete ('{REG_BASE}\\'+$n) /f 2>&1 | Out-Null
  Remove-Item "C:\\etw\\$n.etl" -Force -ErrorAction SilentlyContinue
  Remove-Item "C:\\PerfLogs\\Admin\\$n*.etl" -Force -ErrorAction SilentlyContinue
}}
# VERIFY teardown actually removed the keys
$left = @()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  $q = & $REG query ('{REG_BASE}\\'+$n) /v Start 2>&1 | Out-String
  if($q -match '0x1'){{ $left += $n }}
  # also check the session is really gone
  $s = & $LM query $n 2>&1 | Out-String
  if($s -match '(?i)Running'){{ $left += $n }}
}}
if($left.Count -gt 0){{
  Write-Output "TDFAIL left=$($left -join ',')"
  exit 1
}}
Write-Output 'TORN DOWN'
""".strip()


# ---------------------------------------------------------------- driver

def run_ps(row: dict, script: str) -> dict:
    """Send a PowerShell script to a WinRM witness."""
    import winrm as _winrm
    creds = lib.creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or "basic"
    session = _winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                             transport=transport)
    r = session.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else r.std_out
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else r.std_err
    return {"ok": r.status_code == 0, "stdout": out.strip(), "stderr": err.strip()[:500]}


def main():
    ap = argparse.ArgumentParser(description="rmagent-at autologger management (MOP-level)")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--resize", type=int, default=None, metavar="MB")
    args = ap.parse_args()

    if not (args.setup or args.status or args.teardown):
        ap.error("choose --setup, --status, or --teardown")

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)

    for row in rows:
        wid = row.get("id")
        if args.status:
            res = run_ps(row, _status_ps())
            print(f"[{wid}] {res.get('stdout','')[:300]}")
            continue
        if args.teardown:
            res = run_ps(row, _teardown_ps())
            ok = res['ok'] and 'TORN DOWN' in res.get('stdout','')
            print(f"[{wid}] teardown: {'OK' if ok else 'FAIL: ' + res.get('stdout','')[:150]}")
            continue
        if args.setup:
            for sess in SESSIONS:
                buf = args.resize if args.resize else sess["buffer_mb"]
                script = _setup_ps(sess, buf)
                res = run_ps(row, script)
                line = res.get("stdout", "")
                if "SETUP" in line:
                    print(f"[{wid}] {line}")
                elif "REGFAIL" in line:
                    print(f"[{wid}] REGFAIL {sess['name']}: {line[:150]}")
                elif "LMFAIL" in line:
                    print(f"[{wid}] LMFAIL {sess['name']}: {line[:150]}")
                else:
                    print(f"[{wid}] {sess['name']}: FAIL exit={res.get('stderr','')[:150]}")


if __name__ == "__main__":
    main()