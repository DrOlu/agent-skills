# kill_process - kill a process by PID, recording name + cmdline first (they go to
# the journal via result_detail - a kill cannot be undone, so the evidence must be
# captured BEFORE the process dies). Engine injects $Target (PID).
# REV 17 (C1): WQL filter QUOTED. REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $p = Get-CimInstance Win32_Process -Filter "ProcessId='$Target'" -ErrorAction SilentlyContinue
  if (-not $p) {
    [pscustomobject]@{ action='kill_process'; pid=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    $name = $p.Name
    $cmd  = $p.CommandLine
    $own  = ''
    try { $o = Invoke-CimMethod -InputObject $p -MethodName GetOwner; $own = "$($o.Domain)\$($o.User)" } catch {}
    Stop-Process -Id $Target -Force -ErrorAction Stop
    Start-Sleep -Seconds 1
    $gone = -not (Get-CimInstance Win32_Process -Filter "ProcessId='$Target'" -ErrorAction SilentlyContinue)
    [pscustomobject]@{ action='kill_process'; pid=$Target; name=$name; owner=$own;
                      cmdline=$cmd; status= if($gone){'killed'}else{'failed'} } | ConvertTo-Json -Compress -Depth 3
  }
} catch {
  [pscustomobject]@{ok=$false; action='kill_process'; pid=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
