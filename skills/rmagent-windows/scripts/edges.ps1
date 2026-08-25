# Allowlisted: who did Administrator/SYSTEM touch since $SinceHours. Capped. No full table.
# REV 8: + Kerberos 4768/4769 (pass-the-ticket), +4648 explicit creds, +4672 special privs.
function F($ev,$name){$x=[xml]$ev.ToXml();$ns=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$ns.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$n=$x.SelectSingleNode("//e:Data[@Name='$name']",$ns);if($n){$n.'#text'} else {$null}}
function TT($ev){$t=F $ev 'TargetUserName';if($t){foreach($tr in $Track){if($t -like "*$tr*"){return $true}}};return $false}
$since=(Get-Date).AddHours(-$SinceHours)
$logons=@()
try{$logons=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$since}|Where-Object{TT $_}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'TargetUserName');type=(F $_ 'LogonType');src=(F $_ 'IpAddress');lid=(F $_ 'TargetLogonId');auth=(F $_ 'AuthenticationPackageName')}
})}catch{}
$explicit=@()
try{$explicit=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4648;StartTime=$since}|Where-Object{TT $_}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');who=(F $_ 'SubjectUserName');became=(F $_ 'TargetUserName');dest=(F $_ 'TargetServerName');src=(F $_ 'IpAddress')}
})}catch{}
$privs=@()
try{$privs=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4672;StartTime=$since}|Where-Object{TT $_}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'SubjectUserName');src=(F $_ 'IpAddress');privs=((F $_ 'PrivilegeList') -replace '\s+',',')}
})}catch{}
$kerb=@()
try{$kerb=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4768,4769;StartTime=$since}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');eid=$_.Id;user=(F $_ 'TargetUserName');svc=(F $_ 'ServiceName');src=(F $_ 'IpAddress')}
})}catch{}
$conns=@()
try{
 $owned=@{}
 foreach($p in (Get-CimInstance Win32_Process)){$o=$p.GetOwner().User; if($Track -contains $o){$owned[$p.ProcessId]=$p.Name}}
 $conns=@(Get-NetTCPConnection -State Established|Where-Object{$_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)' -and $owned.ContainsKey($_.OwningProcess)}|Select-Object -First $Limit|ForEach-Object{
  [pscustomobject]@{dest=$_.RemoteAddress;port=$_.RemotePort;pid=$_.OwningProcess;proc=$owned[$_.OwningProcess]}
 })
}catch{}
[pscustomobject]@{skill='edges';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;logons=@($logons);explicit_creds=@($explicit);special_privs=@($privs);kerberos=@($kerb);conns=@($conns)}|ConvertTo-Json -Compress -Depth 4
