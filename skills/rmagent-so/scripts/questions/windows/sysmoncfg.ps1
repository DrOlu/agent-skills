# sysmoncfg — Sysmon config + network-hook health. Read-only, capped. ONE JSON.
# Answers: which config is live, what the rules say, and whether EID3 (the
# network hook that is platform-dead on some Server 2022 builds) is actually
# recording. Formalizes the 2026-09-27 diagnosis into a named question.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$ErrorActionPreference='SilentlyContinue'
$svc = Get-Service Sysmon64 -ErrorAction SilentlyContinue
$conf = (& C:\Windows\Sysmon64.exe -c 2>&1 | Out-String)
$cfgfile = if ($conf -match 'Config file:\s+(\S.*)') { $Matches[1].Trim() }
$cfghash = if ($conf -match 'Config hash:\s+(\S.*)') { $Matches[1].Trim() }
$netdns  = ($conf -split "`r?`n" | Where-Object {$_ -match 'Network connection|DNS lookup'}) -join ' ; '
$rules   = ($conf -split "`r?`n" | Where-Object {$_ -match 'NetworkConnect|DnsQuery'}) -join ' ; '
$ncblock = ''
if ($cfgfile -and (Test-Path $cfgfile)) {
  $raw = Get-Content $cfgfile -Raw
  $m = [regex]::Match($raw, '<NetworkConnect[\s\S]*?</NetworkConnect>')
  if ($m.Success) { $ncblock = $m.Value.Substring(0, [Math]::Min(300, $m.Value.Length)) }
}
# EID3 liveness: any recent network-connect events at all?
$e3 = 0
try { $e3 = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational'; Id=3} -MaxEvents 5).Count } catch {}
# recent event-id distribution (cap 10)
$dist = ''
try {
  $dist = (@(Get-WinEvent -LogName 'Microsoft-Windows-Sysmon/Operational' -MaxEvents 1000) |
    Group-Object Id | Sort-Object Count -Descending | Select-Object -First 10 |
    ForEach-Object { "EID$($_.Name)=$($_.Count)" }) -join ' '
} catch {}
[pscustomobject]@{
  skill='sysmoncfg'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o')
  service=$(if($svc){[string]$svc.Status}else{'not-installed'})
  config_file=$cfgfile; config_hash=$cfghash
  network_and_dns_state=$netdns; rule_group_lines=$rules
  networkconnect_block=$ncblock
  eid3_recent_sample=$e3
  eid_dist_recent=$dist
  note= if($e3 -gt 0){'EID3 recording'}else{'EID3 dark on this platform - network truth via 5156/portproxy probes'}
}|ConvertTo-Json -Compress -Depth 4
