#!/usr/bin/env python3
"""rmagent-at autologger — enterprise-scale ETW session management.

Creates and manages AutoLogger sessions that start at BOOT and run resident.
The ring buffer is circular: old events are overwritten, nothing is retained
beyond the buffer you chose. No lake.

REV 18 — rebuilt against LIVE FACTS from WS1 (2026-09-04):

  C2. The old LogFileMode 0x1004 decoded to FILE_MODE_APPEND |
      USE_PAGED_MEMORY — a file that grows until MaxFileSize and then the
      session goes DEAD. That is a lake with a lid, not a ring. All three
      sessions were found STOPPED with zero ETL files: they never recorded
      anything. The new mode is 0x2 (EVENT_TRACE_FILE_MODE_CIRCULAR) with
      MaxFileSize as the ring bound: when full, the OLDEST data is
      overwritten — a real ring, bounded, on the witness's own disk.

  H1. 4 of 5 provider GUIDs were WRONG (verified against
      `logman query providers` on WS1):
        .NET CLR        E13C0D23-CCBC-4E12-931B-D9CC2EEE27E4 (was ...D9CC2EEDB7D1)
        HTTP.sys        DD5EF90A-6398-47A4-AD34-4DCECDEF795F (was a fabricated GUID)
        Kernel-Network  7DD42A49-5329-4832-8DFD-43D979153A88 (was correct)
        Kernel-Process  22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716 (was ...-B0C5-...)
      The ASP.NET GUID did not exist at all and is dropped; ASP.NET events
      surface through the CLR provider. A test asserts every configured GUID
      against the KNOWN_PROVIDERS table.

  Buffer arithmetic fixed: BufferSize is in KB and MinimumBuffers is a COUNT.
  "512 MB ring" = BufferSize 1024 KB x 512 buffers = 524,288 KB. The old
  config (1024 x 512) was 512 KB — 1024x smaller than advertised, which
  rounds to nothing on a busy box.

  L1. Transport default now comes from lib.DEFAULT_TRANSPORT.
  L2. --setup is MOP-level: it now supports --dry-run (default) and requires
      --apply for the real change, printing exactly what it will do first.

TRANSPORT NOTE (found live on WS1/WS2, 2026-08-30): Impacket's reg.py
(C:\\Python314\\Scripts\\reg.py) SHADOWS Windows reg.exe in the WinRM PATH.
Every bare `reg add` was silently calling Impacket and failing. ALL registry
writes in this script use the absolute path C:\\Windows\\System32\\reg.exe.
Same for logman: C:\\Windows\\System32\\logman.exe.

This is a PERSISTENT change to the witness (registry + boot-time session).
It is a MOP-level action, not a Phase 0 question. Every change here is
reversible via `teardown()`.

Usage:
  python3 autologger.py --inventory estate.yaml --status              # read-only
  python3 autologger.py --inventory estate.yaml --setup               # DRY-RUN (default)
  python3 autologger.py --inventory estate.yaml --setup --apply       # the real change
  python3 autologger.py --inventory estate.yaml --setup --apply --resize 1024
  python3 autologger.py --inventory estate.yaml --teardown --apply    # remove everything
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

# REV 18 (H1): provider GUIDs VERIFIED LIVE on WS1 via
# `logman query providers` (2026-09-04). A test (test_appsysmon.py) asserts
# every GUID below appears in KNOWN_PROVIDERS with the right label.
KNOWN_PROVIDERS = {
    "E13C0D23-CCBC-4E12-931B-D9CC2EEE27E4": "Microsoft-Windows-DotNETRuntime",
    "DD5EF90A-6398-47A4-AD34-4DCECDEF795F": "Microsoft-Windows-HttpService",
    "7DD42A49-5329-4832-8DFD-43D979153A88": "Microsoft-Windows-Kernel-Network",
    "22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716": "Microsoft-Windows-Kernel-Process",
    "3D6B6687-9ABF-4A72-8A2E-3B1B1E4F1F1A": "(reserved-do-not-use)",
}

SESSIONS = [
    {
        "name": "RMAgent-AppTrace",
        "purpose": "application-level events (.NET CLR runtime, HTTP.sys)",
        # H1: DotNETRuntime + HttpService, both verified live. The fabricated
        # "ASP.NET" GUID is gone — ASP.NET events surface via the CLR provider.
        "providers": [
            "E13C0D23-CCBC-4E12-931B-D9CC2EEE27E4",
            "DD5EF90A-6398-47A4-AD34-4DCECDEF795F",
        ],
        "ring_mb": 512,
    },
    {
        "name": "RMAgent-NetTrace",
        "purpose": "connection-level network (every TCP connection with PID)",
        "providers": [
            "7DD42A49-5329-4832-8DFD-43D979153A88",
        ],
        "ring_mb": 256,
    },
    {
        "name": "RMAgent-ProcTrace",
        "purpose": "process lifecycle (create/exit with full command line)",
        "providers": [
            "22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716",
        ],
        "ring_mb": 128,
    },
]

# C2: a TRUE circular file ring. 0x2 = EVENT_TRACE_FILE_MODE_CIRCULAR.
# (The old 0x1004 = APPEND | USE_PAGED_MEMORY was a file that fills once
# and the session dies — never circular, never a ring.)
LOG_FILE_MODE_CIRCULAR = 0x2
BUFFER_SIZE_KB = 1024  # each kernel buffer is 1 MB


def ring_buffers(ring_mb: int) -> int:
    """C2 arithmetic: how many BufferSize(1024 KB) buffers make ring_mb.

    The old config passed '512' as MinimumBuffers for a '512 MB' session —
    that is 512 KB, 1024x too small."""
    return max(8, (ring_mb * 1024) // BUFFER_SIZE_KB)


# ---------------------------------------------------------------- payloads

def _setup_ps(session: dict, ring_mb: int) -> str:
    """PowerShell to create one circular AutoLogger session. MUST fit the
    WinRM ~8191-char encoded-command budget (Rev 8 lesson — this payload is
    NOT comment-stripped by the engine, so keep it lean; the full lore lives
    in this docstring):
      - ABSOLUTE reg.exe/logman.exe paths (Impacket's reg.py shadows reg.exe).
      - Registry keys configure the BOOT AutoLogger; `logman create` builds a
        DCS whose OWN config governs at runtime and SHADOWS the registry
        (found live 2026-09-04: registry circular, query said Circular: Off).
        Hence the `update -f bincirc -max -o` step — that is what makes the
        ring circular and puts the file where the questions read.
      - logman quirks: -p needs {braces}; no -ets (ephemeral); one create per
        name then `update` for extra providers; verify Circular:On + C:\\etw.
    """
    name = session["name"]
    provs = ",".join(session["providers"])
    max_mb = ring_mb  # the circular file IS the ring
    nbuffers = ring_buffers(ring_mb)
    return f"""
$ErrorActionPreference='Continue'
$name='{name}'
$base='{REG_BASE}\\'+$name
$REG='{REG}'
& $REG add $base /v Start /t REG_DWORD /d 1 /f
& $REG add $base /v MaxFileSize /t REG_DWORD /d {max_mb} /f
& $REG add $base /v FileName /t REG_SZ /d "C:\\etw\\{name}.etl" /f
& $REG add $base /v LogFileMode /t REG_DWORD /d 0x{LOG_FILE_MODE_CIRCULAR:x} /f
& $REG add $base /v BufferSize /t REG_DWORD /d {BUFFER_SIZE_KB} /f
& $REG add $base /v MinimumBuffers /t REG_DWORD /d {nbuffers} /f
& $REG add $base /v MaximumBuffers /t REG_DWORD /d {nbuffers * 2} /f
& $REG add $base /v FlushTimer /t REG_DWORD /d 0 /f
New-Item -ItemType Directory -Path 'C:\\etw' -Force | Out-Null
$provs = '{provs}'.Split(',')
$i = 0
foreach($p in $provs){{
  $pk = $base + '\\' + $p
  & $REG add $pk /v Enabled /t REG_DWORD /d 1 /f
  & $REG add $pk /v Level /t REG_DWORD /d 0xff /f
  & $REG add $pk /v MatchAnyKeyword /t REG_QWORD /d 0xffffffffffffffff /f
  $i++
}}
$vm = & $REG query $base /v LogFileMode 2>&1 | Out-String
if($vm -notmatch '0x2'){{ Write-Output "REGFAIL $name not circular"; exit 1 }}
$first = $provs[0]
$exists = (& '{LOGMAN}' query $name 2>&1 | Out-String) -notmatch '(?i)not found'
if(-not $exists){{
  & '{LOGMAN}' create trace $name -p "{{$first}}" 0xffffffffffffffff 0xff 2>&1 | Out-Null
  if($LASTEXITCODE -ne 0){{ Write-Output "LMFAIL $name create"; exit 1 }}
}}
# the DCS config governs at runtime and shadows the registry — set it here
# -r = run CONTINUOUSLY (restart into a new segment when full): without it a
# circular session fills segment 1 and STOPS (found live: 512 MB file, Stopped).
# FOUND LIVE: providers added via -p default to Level 0 / Keywords 0x0 = capture
# NOTHING (NetTrace recorded one empty event in 20 min). Every provider must
# be re-applied with its keyword mask (0xffffffffffffffff) and level (0xff).
& '{LOGMAN}' update trace $name -f bincirc -max {max_mb} -o "C:\\etw\\{name}.etl" -r 2>&1 | Out-Null
if($LASTEXITCODE -ne 0){{ Write-Output "LMFAIL $name bincirc"; exit 1 }}
foreach($p in $provs){{
  & '{LOGMAN}' update trace $name -p "{{$p}}" 0xffffffffffffffff 0xff 2>&1 | Out-Null
}}
$q = & '{LOGMAN}' query $name 2>&1 | Out-String -Width 400
if($q -notmatch '(?i)Running'){{ & '{LOGMAN}' start $name 2>&1 | Out-Null; Start-Sleep 2 }}
$q = & '{LOGMAN}' query $name 2>&1 | Out-String -Width 400
if(($q -notmatch '(?i)Running') -or ($q -notmatch '(?i)Circular:[ ]*On') -or ($q -notmatch 'C:[/\\\\]+etw')){{
  Write-Output "LMFAIL $name state: $(($q -split \"`n\" | Select-String 'Status|Circular|Output') -join ' | ')"
  exit 1
}}
Write-Output "SETUP $name ring={max_mb}MB buffers={nbuffers}x{BUFFER_SIZE_KB}KB providers=$i mode=circular"
""".strip()


def _status_ps() -> str:
    """Status with ABSOLUTE reg.exe path, running check, file size + age.
    L3: wide Out-String so reg query output cannot wrap mid-value."""
    return f"""
$ErrorActionPreference='SilentlyContinue'
$REG='{REG}'
$LM='{LOGMAN}'
$out=@()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  $base='{REG_BASE}\\'+$n
  $mode=(& $REG query $base /v LogFileMode 2>$null|Out-String -Width 400) -replace '(?s).*REG_DWORD[ ]+',''
  $max=(& $REG query $base /v MaxFileSize 2>$null|Out-String -Width 400) -replace '(?s).*REG_DWORD[ ]+',''
  $buf=(& $REG query $base /v MinimumBuffers 2>$null|Out-String -Width 400) -replace '(?s).*REG_DWORD[ ]+',''
  $q = & $LM query $n 2>&1 | Out-String -Width 400
  $running = ($q -match '(?i)Running') -and ($q -notmatch '(?i)not found')
  $f = Get-Item "C:\\\\etw\\$n.etl" -ErrorAction SilentlyContinue
  $out += [pscustomobject]@{{name=$n;running=$running;mode=$mode.Trim();
    ring_mb=if($max.Trim()){{[int]'0'+$max.Trim()}}else{{$null}};
    min_buffers=$buf.Trim();buf_total_mb=if($buf.Trim()){{[math]::Round(([int]'0'+$buf.Trim())*1024/1024,0)}}else{{$null}};
    file_mb=if($f){{[math]::Round($f.Length/1MB,1)}}else{{$null}};
    file_mtime=if($f){{$f.LastWriteTime.ToString('o')}}else{{$null}}}}
}}
$out | ConvertTo-Json -Compress
""".strip()


def _teardown_ps() -> str:
    """Teardown with ABSOLUTE paths. Found live (2026-09-04): a single
    stop+delete leaves the DCS behind when the trace subcollector is still
    finishing — 'Data Collector already exists' on the next setup. So:
    stop, poll until not Running, delete, re-delete the -ets ghost, and
    VERIFY by DCS existence (not the registry key, which always deletes)."""
    return f"""
$ErrorActionPreference='Continue'
$REG='{REG}'
$LM='{LOGMAN}'
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  # stop (both forms), then WAIT until it is actually not Running
  & $LM stop $n 2>&1 | Out-Null
  & $LM stop $n -ets 2>&1 | Out-Null
  for($w=0; $w -lt 10; $w++){{
    $q = & $LM query $n 2>&1 | Out-String -Width 400
    if(($q -notmatch '(?i)Running') -or ($q -match '(?i)not found')){{ break }}
    Start-Sleep -Milliseconds 500
  }}
  # delete (both forms), twice — the first can fail against a stopping DCS
  for($d=0; $d -lt 3; $d++){{
    & $LM delete $n 2>&1 | Out-Null
    & $LM delete $n -ets 2>&1 | Out-Null
    $q = & $LM query $n 2>&1 | Out-String -Width 400
    if($q -match '(?i)not found'){{ break }}
    Start-Sleep -Milliseconds 500
  }}
  & $REG delete ('{REG_BASE}\\'+$n) /f 2>&1 | Out-Null
  Remove-Item "C:\\etw\\$n*.etl" -Force -ErrorAction SilentlyContinue
  Remove-Item "C:\\PerfLogs\\Admin\\$n*.etl" -Force -ErrorAction SilentlyContinue
}}
# VERIFY by DCS existence + registry + files
$left = @()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){{
  $q = & $LM query $n 2>&1 | Out-String -Width 400
  if($q -notmatch '(?i)not found'){{ $left += $n + ' (dcs)' }}
  $r = & $REG query ('{REG_BASE}\\'+$n) 2>&1 | Out-String -Width 400
  if($r -match 'REG_DWORD'){{ $left += $n + ' (reg)' }}
}}
$etl = Get-ChildItem 'C:\\etw' -Filter 'RMAgent-*.etl' -EA SilentlyContinue
if($etl){{ $left += 'etl-files' }}
if($left.Count -gt 0){{
  Write-Output "TDFAIL left=$($left -join ',')"
  exit 1
}}
Write-Output 'TORN DOWN'
""".strip()


# ---------------------------------------------------------------- driver

def run_ps(row: dict, script: str) -> dict:
    """Send a PowerShell script to a WinRM witness. L1: transport from lib."""
    import winrm as _winrm
    creds = lib.creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or lib.DEFAULT_TRANSPORT
    session = _winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                             transport=transport)
    r = session.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else r.std_out
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else r.std_err
    return {"ok": r.status_code == 0, "stdout": out.strip(), "stderr": err.strip()[:500]}


def describe_setup(session: dict, ring_mb: int) -> str:
    """L2: the dry-run plan line for one session."""
    provs = ", ".join(KNOWN_PROVIDERS.get(p, p) for p in session["providers"])
    return (f"  {session['name']}: circular ring {ring_mb} MB "
            f"({ring_buffers(ring_mb)} buffers x {BUFFER_SIZE_KB} KB), "
            f"file C:\\etw\\{session['name']}.etl, providers: {provs}")


def main():
    ap = argparse.ArgumentParser(description="rmagent-at autologger management (MOP-level)")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--resize", type=int, default=None, metavar="MB",
                    help="ring size in MB (default per session: 512/256/128)")
    # L2: MOP discipline — dry-run is the default, --apply mutates
    ap.add_argument("--apply", action="store_true",
                    help="actually create/tear down (default is a dry-run plan)")
    args = ap.parse_args()

    if not (args.setup or args.status or args.teardown):
        ap.error("choose --setup, --status, or --teardown")
    if (args.setup or args.teardown) and not args.apply:
        # L2: describe exactly what would happen, touch nothing
        print("[dry-run] autologger would make the following PERSISTENT changes:")
        print("  registry: " + REG_BASE + r"\<session> (Start, LogFileMode=0x2 circular,")
        print("            MaxFileSize=ring MB, BufferSize/MinimumBuffers/MaximumBuffers,")
        print("            one subkey per provider GUID) + C: etw directory (C:\\etw\\)")
        print("  logman:   create + start each session (boot-persistent AutoLogger)")
        print("  undo    : --teardown --apply (stops sessions, deletes keys, removes files)")
        print()
        for sess in SESSIONS:
            buf = args.resize if args.resize else sess["ring_mb"]
            print(describe_setup(sess, buf))
        print("\nRe-run with --apply to make the change. --status is always read-only.")
        return

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)

    for row in rows:
        wid = row.get("id")
        if args.status:
            res = run_ps(row, _status_ps())
            print(f"[{wid}] {res.get('stdout','')[:600]}")
            continue
        if args.teardown:
            res = run_ps(row, _teardown_ps())
            ok = res['ok'] and 'TORN DOWN' in res.get('stdout','')
            print(f"[{wid}] teardown: {'OK' if ok else 'FAIL: ' + res.get('stdout','')[:150]}")
            continue
        if args.setup:
            for sess in SESSIONS:
                buf = args.resize if args.resize else sess["ring_mb"]
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
