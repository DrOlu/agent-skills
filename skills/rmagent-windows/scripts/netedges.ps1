# netedges — Sysmon ring: connections, DNS, LSASS access, injection, files, registry.
# REV 8: + Sysmon 10 (LSASS = credential dumping T1003), +8 (injection T1055),
#        +11 (dropped payloads), +13 (persistence registry writes).
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
$since=(Get-Date).AddHours(-$SinceHours)
$L='Microsoft-Windows-Sysmon/Operational'
$c=@();try{$c=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=3;StartTime=$since}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');p=(F $_ 'Image');d=(F $_ 'DestinationIp');pt=(F $_ 'DestinationPort')}
})}catch{}
$dns=@();try{$dns=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=22;StartTime=$since}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');p=(F $_ 'Image');q=(F $_ 'QueryName')}
})}catch{}
$ls=@();try{$ls=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=10;StartTime=$since}|Select-Object -First $Limit|Where-Object{(F $_ 'TargetImage') -match 'lsass'}|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');src=(F $_ 'SourceImage');g=(F $_ 'GrantedAccess')}
})}catch{}
$inj=@();try{$inj=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=8;StartTime=$since}|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');src=(F $_ 'SourceImage');tgt=(F $_ 'TargetImage')}
})}catch{}
$fc=@();try{$fc=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=11;StartTime=$since}|Select-Object -First $Limit|Where-Object{(F $_ 'TargetFilename') -match 'Temp|ProgramData|Public|AppData'}|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');p=(F $_ 'Image');f=(F $_ 'TargetFilename')}
})}catch{}
$rs=@();try{$rs=@(Get-WinEvent -FilterHashtable @{LogName=$L;Id=13;StartTime=$since}|Select-Object -First $Limit|Where-Object{(F $_ 'TargetObject') -match 'Run|IFEO|Winlogon|SecurityPackages'}|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');p=(F $_ 'Image');k=(F $_ 'TargetObject')}
})}catch{}
[pscustomobject]@{skill='netedges';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;conns=@($c);dns_queries=@($dns);lsass_access=@($ls);thread_injection=@($inj);file_creates=@($fc);registry_sets=@($rs)}|ConvertTo-Json -Compress -Depth 4
