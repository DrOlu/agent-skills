# Allowlisted: who did Administrator/SYSTEM touch since $SinceHours. Capped. No full table.
# Returns recent tracked logons (with source) + outbound connections owned by tracked principals.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
function Get-EvField($ev, $name) {
  $x = [xml]$ev.ToXml()
  $ns = New-Object System.Xml.XmlNamespaceManager($x.NameTable)
  $ns.AddNamespace('e', 'http://schemas.microsoft.com/win/2004/08/events/event')
  $n = $x.SelectSingleNode("//e:Data[@Name='$name']", $ns)
  if ($n) { $n.'#text' } else { $null }
}
function Match-Track($ev) {
  foreach ($v in $ev.Properties.Value) { if ($Track -contains $v) { return $true } }
  return $false
}
$since = (Get-Date).AddHours(-$SinceHours)

# --- recent Administrator/SYSTEM logons with source IP + logon id ---
$logons = @()
try {
  $logons = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624; StartTime=$since} |
              Where-Object { Match-Track $_ } |
              Select-Object -First $Limit |
              ForEach-Object {
                [pscustomobject]@{
                  t      = $_.TimeCreated.ToString('o')
                  user   = (Get-EvField $_ 'TargetUserName')
                  type   = (Get-EvField $_ 'LogonType')
                  src    = (Get-EvField $_ 'IpAddress')
                  lid    = (Get-EvField $_ 'TargetLogonId')
                }
              })
} catch {}

# --- outbound remote connections owned by SYSTEM/Administrator processes ---
$conns = @()
try {
  $owned = @{}
  foreach ($p in (Get-CimInstance Win32_Process)) {
    $o = $p.GetOwner().User
    if ($Track -contains $o) { $owned[$p.ProcessId] = ($p.Name) }
  }
  $conns = @(Get-NetTCPConnection -State Established |
             Where-Object { $_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)' -and $owned.ContainsKey($_.OwningProcess) } |
             Select-Object -First $Limit |
             ForEach-Object {
               [pscustomobject]@{
                 dest = $_.RemoteAddress
                 port = $_.RemotePort
                 pid  = $_.OwningProcess
                 proc = $owned[$_.OwningProcess]
               }
             })
} catch {}

[pscustomobject]@{
  skill  = 'edges'
  host   = $env:COMPUTERNAME
  utc    = [DateTime]::UtcNow.ToString('o')
  since  = $since.ToString('o')
  track  = $Track
  logons = @($logons)
  conns  = @($conns)
} | ConvertTo-Json -Compress -Depth 4
