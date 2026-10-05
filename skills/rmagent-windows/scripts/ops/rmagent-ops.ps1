<#
.SYNOPSIS
  rmagent enterprise PS-native kit — ring health / doctor / watchdog without Python.

.DESCRIPTION
  For enterprises where Python is not permitted on Windows witnesses. Mirrors the
  rmagent-at autologger (status/doctor/watchdog) using only PowerShell 5.1 +
  stock tools (logman.exe, schtasks.exe, reg.exe, Get-WinEvent). Reads the ring
  names/caps from the same sessions rmagent creates (RMAgent-AppTrace/NetTrace/
  ProcTrace). All output is ONE JSON object, same contract as the Phase-0 questions.

.PARAMETER Action
  status | doctor | watchdog | watchdog-status | watchdog-remove | watch-once

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File rmagent-ops.ps1 status
  powershell -NoProfile -ExecutionPolicy Bypass -File rmagent-ops.ps1 doctor          # report only
  powershell -NoProfile -ExecutionPolicy Bypass -File rmagent-ops.ps1 doctor -Apply   # archive + restart
  powershell -NoProfile -ExecutionPolicy Bypass -File rmagent-ops.ps1 watchdog -Apply # install 5-min task
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][ValidateSet('status','doctor','watchdog','watchdog-status','watchdog-remove','watch-once')][string]$Action,
  [switch]$Apply
)

$ErrorActionPreference = 'SilentlyContinue'
$LOGMAN = 'C:\Windows\System32\logman.exe'
$SCH    = 'C:\Windows\System32\schtasks.exe'
$SESSIONS = @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')

# ---------- shared: read one session (mirrors ringhealth.ps1 verdict logic) ----------
function Get-RingState {
  param([string]$Name)
  $q = & $LOGMAN query $Name 2>$null | Out-String -Width 400
  $running = ($q -match '(?i)Running')
  $cap = 0; $base = ''; $written = $null; $lost = $null
  if ($q -match '(?i)Segment Max Size:\s+(\d+)\s*MB') { $cap = [int]$Matches[1] }
  if ($q -match '(?i)(?:File Name|Output Location):\s+(\S+)') { $base = $Matches[1] }
  if ($q -match '(?i)Buffers Lost:\s+(\d+)')    { $lost = [int]$Matches[1] }
  if ($q -match '(?i)Buffers Written:\s+(\d+)') { $written = [int]$Matches[1] }
  # segment resolution: base ALREADY carries _NNNNNN; glob only when it does not
  $seg = $base
  $dir = Split-Path $base -Parent; $leaf = [IO.Path]::GetFileNameWithoutExtension($base)
  if ($dir -and $leaf -and ($leaf -notmatch '_\d{6}$')) {
    $newest = Get-ChildItem (Join-Path $dir ($leaf + '_*.etl')) -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) { $seg = $newest.FullName }
  }
  $bytes = 0; $ageMin = $null; $file = ''
  if ($seg -and (Test-Path $seg)) {
    $item = Get-Item $seg
    $file = $seg; $bytes = $item.Length
    $ageMin = [math]::Round((New-TimeSpan -Start $item.LastWriteTime.ToUniversalTime() -End ([DateTime]::UtcNow)).TotalMinutes, 1)
  }
  $frozen = $running -and ($cap -gt 0) -and ($bytes -ge ($cap * 1MB * 0.98))
  [pscustomobject]@{
    session=$Name; status=$(if($running){'Running'}elseif($q -match '(?i)Stopped'){'Stopped'}else{'missing'})
    circular=$(if($q -match 'Circular'){'On'}else{'unknown'}); bytes=$bytes; file=$file; cap_mb=$cap
    mtime_age_min=$ageMin; stale=$(if($ageMin -gt 30){$true}else{$false})
    frozen=$frozen; buffers_written=$written; buffers_lost=$lost
  }
}

# ---------- restart: stop -ets, archive frozen segment, start ----------
function Restart-Ring {
  param([string]$Name, [object]$State)
  $null = & $LOGMAN stop $Name -ets 2>&1
  Start-Sleep -Seconds 2
  $arch = ''
  if ($State.frozen -and $State.file -and (Test-Path $State.file)) {
    try {
      $ts = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmss')
      $arch = "$($State.file).frozen-$ts"
      Move-Item -Path $State.file -Destination $arch -Force -ErrorAction Stop
    } catch { $arch = '' }
  }
  $null = & $LOGMAN start $Name 2>&1
  Start-Sleep -Seconds 3
  $q2 = & $LOGMAN query $Name 2>$null | Out-String -Width 400
  return @{
    restarted = ($q2 -match '(?i)Running')
    archived  = $arch
  }
}

# ---------- actions ----------
switch ($Action) {
  'status' {
    $rows = foreach ($n in $SESSIONS) { Get-RingState $n }
    $frozen = @($rows | Where-Object { $_.frozen }).Count
    $down   = @($rows | Where-Object { $_.status -ne 'Running' }).Count
    [pscustomobject]@{
      skill='rmagent-ops-status'; host=$env:COMPUTERNAME; utc=(Get-Date).ToUniversalTime().ToString('o')
      sessions=$rows; blind_count=($frozen + $down); frozen_count=$frozen
      blind_check=$(if (($frozen + $down) -eq 0) {'ok'} else {'BLIND'})
      note='Stopped OR frozen-at-cap ring = blind. buffers_written=0 on a fresh/quiet ring is kernel buffering, not death.'
    } | ConvertTo-Json -Depth 5
  }

  { $_ -eq 'doctor' -or $_ -eq 'watch-once' } {
    $found = @(); $restarted = @(); $failed = @(); $healthy = @()
    foreach ($n in $SESSIONS) {
      $s = Get-RingState $n
      if ($s.frozen -or ($s.status -ne 'Running')) {
        $found += "$n $(if($s.frozen){'frozen-at-cap ' + $s.bytes + '/' + $s.cap_mb + 'MB'}else{$s.status})"
        if ($Apply) {
          $r = Restart-Ring $n $s
          if ($r.restarted) { $restarted += "$n -> Running$(if($r.archived){' [archived ' + (Split-Path $r.archived -Leaf) + ']'})" }
          else { $failed += "$n restart failed" }
        }
      } else { $healthy += $n }
    }
    [pscustomobject]@{
      skill='rmagent-ops-doctor'; host=$env:COMPUTERNAME; utc=(Get-Date).ToUniversalTime().ToString('o')
      apply=[bool]$Apply; found=$found; restarted=$restarted; healthy=$healthy; failed=$failed
    } | ConvertTo-Json -Depth 5
  }

  'watchdog' {
    if (-not $Apply) {
      Write-Output "DRY-RUN: would install scheduled task 'RMAgent-RingWatchdog' (SYSTEM, every 5 min) running C:\etw\rmagent-watchdog.ps1; log C:\etw\watchdog.log (200-line cap). Re-run with -Apply."
      return
    }
    $guardPath = 'C:\etw\rmagent-watchdog.ps1'
    $guard = @'
$ErrorActionPreference='SilentlyContinue'
$LOGMAN='C:\Windows\System32\logman.exe'
$log='C:\etw\watchdog.log'
$stamp=(Get-Date).ToUniversalTime().ToString('s')+'Z'
$entries=@()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){
  $q = & $LOGMAN query $n 2>$null | Out-String -Width 400
  $running = ($q -match '(?i)Running')
  $cap=0; $base=''
  if($q -match '(?i)Segment Max Size:\s+(\d+)\s*MB'){ $cap=[int]$Matches[1] }
  if($q -match '(?i)(?:File Name|Output Location):\s+(\S+)'){ $base=$Matches[1] }
  $seg=$base
  $dir=Split-Path $base -Parent; $leaf=[IO.Path]::GetFileNameWithoutExtension($base)
  if($dir -and $leaf -and ($leaf -notmatch '_\d{6}$')){
    $newest=Get-ChildItem (Join-Path $dir ($leaf+'_*.etl')) -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if($newest){ $seg=$newest.FullName }
  }
  $bytes=0
  if($seg -and (Test-Path $seg)){ $bytes=(Get-Item $seg).Length }
  $frozen = $running -and ($cap -gt 0) -and ($bytes -ge ($cap*1MB*0.98))
  if($frozen -or (-not $running)){
    $why = $(if($frozen){'frozen-at-cap'})+$(if(-not $frozen){'stopped'})
    $null = & $LOGMAN stop $n -ets 2>&1
    Start-Sleep -Seconds 2
    if($frozen -and $seg -and (Test-Path $seg)){
      try{ $ts=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmss'); Move-Item -Path $seg -Destination "$seg.frozen-$ts" -Force -EA Stop }catch{}
    }
    $null = & $LOGMAN start $n 2>&1
    Start-Sleep -Seconds 3
    $q2 = & $LOGMAN query $n 2>$null | Out-String -Width 400
    $ok2 = ($q2 -match '(?i)Running')
    $entries += "$stamp $n $why $(if($ok2){'restarted->Running'}else{'RESTART-FAILED'})"
  }
}
if($entries.Count -gt 0){
  Add-Content -Path $log -Value $entries
  $all = Get-Content $log -EA SilentlyContinue
  if($all.Count -gt 200){ $all | Select-Object -Last 200 | Set-Content $log }
}
'@
    $null = New-Item -Path 'C:\etw' -ItemType Directory -Force
    Set-Content -Path $guardPath -Value $guard -Encoding UTF8
    $null = & $SCH /Create /F /TN RMAgent-RingWatchdog /RU SYSTEM /SC MINUTE /MO 5 /TR "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $guardPath" 2>&1
    $null = & $SCH /Run /TN RMAgent-RingWatchdog 2>&1
    $q = & $SCH /Query /TN RMAgent-RingWatchdog 2>&1 | Out-String -Width 300
    [pscustomobject]@{
      skill='rmagent-ops-watchdog'; host=$env:COMPUTERNAME
      installed=($q -match 'RMAgent-RingWatchdog'); guard=$guardPath; log='C:\etw\watchdog.log'
      interval_min=5; run_as='SYSTEM'
    } | ConvertTo-Json -Depth 3
  }

  'watchdog-status' {
    $q = & $SCH /Query /TN RMAgent-RingWatchdog 2>&1 | Out-String -Width 400
    $present = ($q -match 'RMAgent-RingWatchdog')
    $log = @()
    if (Test-Path 'C:\etw\watchdog.log') { $log = Get-Content 'C:\etw\watchdog.log' -Tail 5 }
    [pscustomobject]@{ task=$(if($present){'present'}else{'absent'}); recent_log=$log } | ConvertTo-Json -Compress
  }

  'watchdog-remove' {
    $null = & $SCH /Delete /TN RMAgent-RingWatchdog /F 2>&1
    $q = & $SCH /Query /TN RMAgent-RingWatchdog 2>&1 | Out-String
    [pscustomobject]@{ removed = -not ($q -match 'RMAgent-RingWatchdog') } | ConvertTo-Json -Compress
  }
}
