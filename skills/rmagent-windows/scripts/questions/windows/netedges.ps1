# netedges — SYSTEM/Administrator-owned outbound connections from the Sysmon EID3 ring.
# Unlike `edges` (point-in-time Get-NetTCPConnection), this reads the Sysmon
# Microsoft-Windows-Sysmon/Operational log (Id=3 NetworkConnect) — a RING that
# persists transient connections after they close. Capped. No dump.
# Requires Sysmon with <NetworkConnect onmatch="exclude"> (log all) enabled.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($u){ if(-not $u){return $false}; foreach($t in $Track){ if($u -like "*$t*"){return $true} }; return $false }
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

[pscustomobject]@{
  skill = 'netedges'
  host  = $env:COMPUTERNAME
  utc   = [DateTime]::UtcNow.ToString('o')
  since = $since.ToString('o')
  track = $Track
  conns = @($conns)
} | ConvertTo-Json -Compress -Depth 4
