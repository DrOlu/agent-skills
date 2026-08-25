# Allowlisted: compact Administrator/SYSTEM smoke for the last window. Counts + short names.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# FIXES (2026-08-19): (1) match only TargetUserName on 4625 — matching any field
# counted SYSTEM-subject events as admin failures; (2) new_local_admins only reports
# members STILL in the group — deleted drill users lingered as stale SIDs for 24h.
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($ev){$t=F $ev 'TargetUserName';if($t){foreach($tr in $Track){if($t -like "*$tr*"){return $true}}};return $false}
$now=[DateTime]::UtcNow; $since=$now.AddHours(-$SinceHours)

$failed=0
try{$failed=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$since}|Where-Object{MT $_}).Count}catch{}

$cur=@(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue)
$newAdmins=@()
try{
 $newAdmins=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4732;StartTime=$now.AddHours(-24)}|Select-Object -First $Limit|ForEach-Object{
   $mn=F $_ 'MemberName';$r=$null
   if($mn -and $mn -ne '-'){$r=$mn}
   else{$s=F $_ 'MemberSid';if($s -and $s -ne '-'){try{$r=[System.Security.Principal.SecurityIdentifier]::new($s).Translate([System.Security.Principal.NTAccount]).Value}catch{}}}
   if($r -and @($cur|Where-Object{$_.Name -eq $r -or $_.Name -match "\\$r`$"}).Count){$r}
 }|Select-Object -Unique)
}catch{}

$svc=@()
try{$svc=@(Get-CimInstance Win32_Service -Filter "State='Running'"|Where-Object{$_.StartName -match 'LocalSystem|Administrator'}|Select-Object -First $Limit -ExpandProperty Name)}catch{}

$svcNew=0;$taskNew=0
try{$svcNew=@(Get-WinEvent -FilterHashtable @{LogName='System';Id=7045;StartTime=$since}).Count}catch{}
try{$taskNew=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4698;StartTime=$since}).Count}catch{}

[pscustomobject]@{skill='sketch';host=$env:COMPUTERNAME;utc=$now.ToString('o');window_hours=$SinceHours;track=$Track;admin_failed=$failed;admin_failed_attack='T1110';new_local_admins=@($newAdmins);new_local_admins_attack='T1136.001';running_priv_svcs=@($svc);new_services=$svcNew;new_services_attack='T1543.003';new_tasks=$taskNew;new_tasks_attack='T1053.005'}|ConvertTo-Json -Compress -Depth 3
