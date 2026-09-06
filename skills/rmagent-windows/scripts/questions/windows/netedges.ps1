# netedges — SYSTEM/Administrator-owned outbound connections from the Sysmon EID3 ring.
# REV 3 (2026-08-19): + Sysmon 22 DNS queries (C2 domain resolution) — the domain
# a beacon resolves BEFORE the connection. Pair a DNS query with the netedges conn
# and you have the full C2 story. Requires Sysmon with <DnsQuery onmatch="exclude">.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($u){ if(-not $u){return $false}; foreach($t in $Track){ if((($u -split '\\')[-1]) -eq $t){return $true} }; return $false }
$since = (Get-Date).AddHours(-$SinceHours)
$conns = @()
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

[pscustomobject]@{
  skill = 'netedges'
  host  = $env:COMPUTERNAME
  utc   = [DateTime]::UtcNow.ToString('o')
  since = $since.ToString('o')
  track = $Track
  conns = @($conns)
  dns_queries = @($dns)
} | ConvertTo-Json -Compress -Depth 4
