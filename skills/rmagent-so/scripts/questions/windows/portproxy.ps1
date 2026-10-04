# portproxy — the netsh portproxy relay table, with liveness + relay activity.
# Read-only, capped. ONE JSON. Formalizes the 2026-09-28 DC1 investigation:
# public listen ports forwarded to local backends, which backends are dead,
# and how much relay traffic the 5156 audit stream shows for each.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$ErrorActionPreference='SilentlyContinue'
function XF($e,$n){try{$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}catch{}}
$pp = (netsh interface portproxy show all 2>&1 | Out-String)
$rows = @()
foreach ($m in [regex]::Matches($pp, '([\d.]+)\s+(\d+)\s+([\d.]+)\s+(\d+)')) {
  $la = $m.Groups[1].Value; $lp = [int]$m.Groups[2].Value
  $ca = $m.Groups[3].Value; $cp = [int]$m.Groups[4].Value
  $listen  = @(Get-NetTCPConnection -LocalPort $lp -State Listen -ErrorAction SilentlyContinue).Count
  $backend = @(Get-NetTCPConnection -LocalPort $cp -State Listen -ErrorAction SilentlyContinue).Count
  $since = (Get-Date).AddHours(-[double]$SinceHours)
  $act = 0; $blocked = 0
  try {
    $ev = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5156; StartTime=$since} -MaxEvents 4000)
    $act = @($ev | Where-Object { (XF $_ 'DestPort') -eq "$cp" }).Count
  } catch {}
  try {
    $ev2 = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5157; StartTime=$since} -MaxEvents 2000)
    $blocked = @($ev2 | Where-Object { (XF $_ 'DestPort') -eq "$cp" }).Count
  } catch {}
  $rows += [pscustomobject]@{
    listen="$la`:$lp"; backend="$ca`:$cp"
    listen_bound=$listen; backend_listeners=$backend
    relays_5156=$act; blocked_5157=$blocked
    verdict= if($backend -gt 0){'live'}else{'dead-backend'}
  }
}
[pscustomobject]@{
  skill='portproxy'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o')
  rules=@($rows).Count; rows=@($rows | Select-Object -First $Limit)
  note='netsh portproxy store: HKLM\SYSTEM\CurrentControlSet\Services\PortProxy\v4tov4 (iphlpsvc relays)'
}|ConvertTo-Json -Compress -Depth 4
