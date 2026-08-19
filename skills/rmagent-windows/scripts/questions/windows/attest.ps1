# Allowlisted: alive + Administrator/SYSTEM smoke. Digest only. No dump.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
function Match-Track($ev) {
  foreach ($v in $ev.Properties.Value) { if ($Track -contains $v) { return $true } }
  return $false
}
$now = [DateTime]::UtcNow
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime

$failed = 0
$ok = 0
try {
  $failed = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=$now.AddSeconds(-60)} |
              Where-Object { Match-Track $_ }).Count
} catch {}
try {
  $ok = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624; StartTime=$now.AddMinutes(-5)} |
          Where-Object { Match-Track $_ }).Count
} catch {}

$lac = 0
try { $lac = @(Get-LocalGroupMember -Group Administrators).Count } catch {}

# SYSTEM/Admin-owned processes with at least one ESTABLISHED remote connection
$sysconn = 0
try {
  $ownedPids = @(Get-CimInstance Win32_Process | Where-Object {
    $o = $_.GetOwner().User; $Track -contains $o
  } | Select-Object -ExpandProperty ProcessId)
  $sysconn = @(Get-NetTCPConnection -State Established |
               Where-Object { $_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)' -and $ownedPids -contains $_.OwningProcess } |
               Select-Object -Unique RemoteAddress).Count
} catch {}

[pscustomobject]@{
  skill               = 'attest'
  host                = $env:COMPUTERNAME
  utc                 = $now.ToString('o')
  alive               = $true
  last_boot           = $boot.ToString('o')
  track               = $Track
  admin_failed_60s    = $failed
  admin_ok_5min       = $ok
  local_admin_count   = $lac
  system_remote_conns = $sysconn
} | ConvertTo-Json -Compress
