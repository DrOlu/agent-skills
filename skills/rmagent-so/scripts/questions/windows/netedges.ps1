# netedges — SYSTEM/Administrator-owned outbound connections from the Sysmon EID3 ring.
# REV 3 (2026-08-19): + Sysmon 22 DNS queries (C2 domain resolution) — the domain
# a beacon resolves BEFORE the connection. Pair a DNS query with the netedges conn
# and you have the full C2 story. Requires Sysmon with <DnsQuery onmatch="exclude">.
# REV 4 (2026-09-27): honest fallback when Sysmon EID3 cannot arm (platform WFP-hook
# bug, e.g. CORP-DC1 / Server 2022 + Sysmon 15.15): Security-log 5156/5157 events
# (Filtering Platform Connection/Packet Drop auditing) carry the same story with
# process + principal. conns_source records which sensor answered. 5157 blocked
# connections are ALWAYS reported when present — they are detection gold.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($u){ if(-not $u){return $false}; foreach($t in $Track){ if((($u -split '\\')[-1]) -eq $t){return $true} }; return $false }
$since = (Get-Date).AddHours(-$SinceHours)
$conns = @()
$conns_source = 'sysmon-eid3'
try {
  $conns = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational'; Id=3; StartTime=$since} |
            Select-Object -First $Limit |
            Where-Object { MT (F $_ 'User') } |
            ForEach-Object {
              [pscustomobject]@{
                t    = $_.TimeCreated.ToString('o')
                proc = (F $_ 'Image')
                user = (F $_ 'User')
                dest = (F $_ 'DestinationIp')
                port = (F $_ 'DestinationPort')
              }
            })
} catch {}

# REV 4 fallback: Sysmon EID3 dark → read Security 5156 (allowed connections)
# for tracked principals. Same row shape; source recorded honestly.
if ($conns.Count -eq 0) {
  $conns_source = 'audit-5156'
  try {
    # outbound only (%%14593); kernel-mode rows carry an empty SubjectUserName
    # on this platform - keep them, marked '(kernel)', so the cap bounds noise
    $conns = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5156; StartTime=$since} |
              Select-Object -First ($Limit * 3) |
              Where-Object { (F $_ 'Direction') -eq '%%14593' } |
              Select-Object -First $Limit |
              ForEach-Object {
                $u = F $_ 'SubjectUserName'
                [pscustomobject]@{
                  t    = $_.TimeCreated.ToString('o')
                  proc = (F $_ 'Application')
                  user = if($u){$u}else{'(kernel)'}
                  dest = (F $_ 'DestAddress')
                  port = (F $_ 'DestPort')
                }
              })
  } catch { $conns_source = 'sysmon-eid3 (empty)' }
  if ($conns.Count -eq 0 -and $conns_source -eq 'audit-5156') { $conns_source = 'audit-5156 (empty)' }
}

# Sysmon 22 DNS queries by tracked principals — what domains did they resolve?
$dns = @()
try {
  $dns = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational'; Id=22; StartTime=$since} |
           Select-Object -First $Limit |
           Where-Object { MT (F $_ 'User') } |
           ForEach-Object {
             [pscustomobject]@{
               t      = $_.TimeCreated.ToString('o')
               proc   = (F $_ 'Image')
               user   = (F $_ 'User')
               query  = (F $_ 'QueryName')
               result = (F $_ 'QueryResults')
             }
           })
} catch {}

# REV 4: blocked connections (Security 5157) — always read, both principals.
# A tracked principal's connection the firewall REFUSED is a finding, not noise.
$blocked = @()
try {
  $blocked = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5157; StartTime=$since} |
               Select-Object -First $Limit |
               ForEach-Object {
                 [pscustomobject]@{
                   t    = $_.TimeCreated.ToString('o')
                   proc = (F $_ 'Application')
                   user = (F $_ 'SubjectUserName')
                   dest = (F $_ 'DestAddress')
                   port = (F $_ 'DestPort')
                 }
               })
} catch {}

[pscustomobject]@{
  skill = 'netedges'
  host  = $env:COMPUTERNAME
  utc   = [DateTime]::UtcNow.ToString('o')
  since = $since.ToString('o')
  track = $Track
  conns_source = $conns_source
  conns = @($conns)
  dns_queries = @($dns)
  blocked_conns = @($blocked)
} | ConvertTo-Json -Compress -Depth 4
