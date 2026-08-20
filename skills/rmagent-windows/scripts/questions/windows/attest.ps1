# Allowlisted: alive + Administrator/SYSTEM smoke. Digest only. No dump.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# BUG FIX (2026-08-19): Match-Track used to match ANY event field equal to a tracked
# name — including SubjectUserName (the account that PERFORMED the action). A service
# running as SYSTEM touching any user would light up "admin activity". We now match
# only the TARGET user of the event (TargetUserName for 4624/4625).
function Get-EvField($ev, $name) {
  $x = [xml]$ev.ToXml()
  $ns = New-Object System.Xml.XmlNamespaceManager($x.NameTable)
  $ns.AddNamespace('e', 'http://schemas.microsoft.com/win/2004/08/events/event')
  $n = $x.SelectSingleNode("//e:Data[@Name='$name']", $ns)
  if ($n) { $n.'#text' } else { $null }
}
function Match-TargetTrack($ev) {
  $t = Get-EvField $ev 'TargetUserName'
  if ($t) { foreach ($tr in $Track) { if ($t -like "*$tr*") { return $true } } }
  return $false
}
$now = [DateTime]::UtcNow
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime

$failed = 0
$ok = 0
try {
  $failed = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=$now.AddSeconds(-60)} |
              Where-Object { Match-TargetTrack $_ }).Count
} catch {}
try {
  $ok = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624; StartTime=$now.AddMinutes(-5)} |
          Where-Object { Match-TargetTrack $_ }).Count
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

# Sysmon health — the tripwire that tells you when to fall back to kernring.
# An attacker who deletes Sysmon (Stop-Service Sysmon64; sc.exe delete Sysmon64)
# changes this from "Running" to "not-installed". That change is a finding.
$sysmon = 'unknown'
try {
  $svc = Get-Service Sysmon64,Sysmon -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($svc) { $sysmon = "$($svc.Name)=$($svc.Status)" } else { $sysmon = 'not-installed' }
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
  sysmon_status       = $sysmon
} | ConvertTo-Json -Compress
