# profile — on-device resource profiling. Read-only, no config changes.
# CPU / memory / disk / process inventory in ONE capped payload, plus the
# identity x resource join: which processes run as a TRACKED principal.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now = [DateTime]::UtcNow

# --- CPU (machine load, averaged across sockets) ---
$cpu = $null
try { $cpu = [math]::Round((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average, 1) } catch {}

# --- top processes by instantaneous CPU% (PerfProc, not cumulative) ---
$topcpu = @()
try {
  $topcpu = @(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -Filter 'IDProcess != 0' |
    Sort-Object -Property PercentProcessorTime -Descending | Select-Object -First $Limit | ForEach-Object {
      $p = Get-Process -Id $_.IDProcess -ErrorAction SilentlyContinue
      [pscustomobject]@{ n = $_.Name; pid = $_.IDProcess; cpu = [int]$_.PercentProcessorTime; mem = $(if ($p) { [math]::Round($p.WorkingSet64 / 1MB, 0) } else { $null }) }
    })
} catch {}

# --- memory (total/free/used%) ---
$mem = $null
try {
  $os = Get-CimInstance Win32_OperatingSystem
  $t = [math]::Round($os.TotalVisibleMemorySize / 1KB, 0)
  $f = [math]::Round($os.FreePhysicalMemory / 1KB, 0)
  $mem = @{ total_mb = $t; free_mb = $f; used_pct = [math]::Round((($t - $f) / $t) * 100, 1) }
} catch {}

# --- top processes by working set ---
$topmem = @()
try {
  $topmem = @(Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First $Limit | ForEach-Object {
    [pscustomobject]@{ n = $_.Name; pid = $_.Id; mem = [math]::Round($_.WorkingSet64 / 1MB, 0) }
  })
} catch {}

# --- disk volumes (local fixed drives) ---
$disks = @()
try {
  $disks = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType = 3' | ForEach-Object {
    $u = $(if ($_.Size) { [math]::Round((($_.Size - $_.FreeSpace) / $_.Size) * 100, 1) } else { $null })
    [pscustomobject]@{ d = $_.DeviceID; total_gb = [math]::Round($_.Size / 1GB, 1); free_gb = [math]::Round($_.FreeSpace / 1GB, 1); used_pct = $u }
  })
} catch {}

# --- process inventory count ---
$pc = 0
try { $pc = (Get-Process).Count } catch {}

# --- the join: tracked-principal processes (Administrator/SYSTEM) by memory ---
# BUG FIX (rev 14): Get-CimInstance ... .GetOwner().User returns '' on Server
# 2022 via WinRM — every process looked unowned. Invoke-CimMethod works and
# returns DOMAIN\user, so match on the bare name suffix against $Track.
$tracked = @()
try {
  $tracked = @(Get-CimInstance Win32_Process | ForEach-Object {
    $o = Invoke-CimMethod -InputObject $_ -MethodName GetOwner
    $u = $o.User
    if ($u) {
      $bare = ($u -split '\\')[-1]
      if ($Track -contains $bare) {
        [pscustomobject]@{ n = $_.Name; pid = $_.ProcessId; owner = $bare; mem = [math]::Round($_.WorkingSetSize / 1MB, 0) }
      }
    }
  } | Sort-Object mem -Descending | Select-Object -First $Limit)
} catch {}

[pscustomobject]@{
  skill        = 'profile'
  host         = $env:COMPUTERNAME
  utc          = $now.ToString('o')
  track        = $Track
  cpu_pct      = $cpu
  mem          = $mem
  disks        = $disks
  proc_count   = $pc
  top_cpu      = $topcpu
  top_mem      = $topmem
  tracked_procs = $tracked
} | ConvertTo-Json -Compress -Depth 4
