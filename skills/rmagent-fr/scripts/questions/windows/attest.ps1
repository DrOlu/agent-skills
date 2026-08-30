# attest — alive + Administrator/SYSTEM smoke + blind check + log edge. Digest only.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList
# Match-TargetTrack matches ONLY TargetUserName (not SubjectUserName) so a
# SYSTEM service touching a user doesn't light up as "admin activity".
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($e){$t=F $e 'TargetUserName';if($t){foreach($tr in $Track){if($t -like "*$tr*"){return $true}}};return $false}
$now=[DateTime]::UtcNow
$boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$failed=0;$ok=0
try{$failed=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$now.AddSeconds(-60)}|?{MT $_}).Count}catch{}
try{$ok=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddMinutes(-5)}|?{MT $_}).Count}catch{}
$lac=0
try{$lac=@(Get-LocalGroupMember -Group Administrators).Count}catch{}
# SYSTEM/tracked-owned processes with an ESTABLISHED remote connection.
# Invoke-CimMethod (not .GetOwner().User, which returns '' on 2022 via WinRM).
$sysconn=0
try{
  $op=@(Get-CimInstance Win32_Process|%{$u=(Invoke-CimMethod -InputObject $_ -MethodName GetOwner).User;if($u -and ($Track -contains ($u -split '\\')[-1])){$_.ProcessId}})
  $sysconn=@(Get-NetTCPConnection -State Established|?{$_.RemoteAddress -notmatch '^(127\.|0\.|::)' -and $op -contains $_.OwningProcess}|Select -Unique RemoteAddress).Count
}catch{}
# Sysmon health — the tripwire that says when to fall back to kernring.
$sysmon='unknown'
try{$svc=Get-Service Sysmon64,Sysmon -EA SilentlyContinue|Select -First 1;if($svc){$sysmon="$($svc.Name)=$($svc.Status)"}else{$sysmon='not-installed'}}catch{}
# blind_check — can this witness actually SEE? (WS2 was blind: Logon audit
# Failure-only → edges returned ZERO logons while connected.)
$bw='Logon','Logoff','Special Logon','Other Logon/Logoff Events','Group Membership','Account Lockout'
$blind=@{}
try{foreach($l in (auditpol /get /category:* /r 2>$null)){$p=$l -split ',';if($p.Count -ge 5 -and ($bw -contains $p[2].Trim('"'))){$blind[$p[2].Trim('"')]=$(if($p[4].Trim('"') -match 'Success'){'ok'}else{'BLIND'})}}}catch{}
foreach($w in $bw){if(-not $blind.ContainsKey($w)){$blind[$w]='unknown'}}
$blindCount=@($blind.Values|?{$_ -like 'BLIND*'}).Count
$raw4624=0
try{$raw4624=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddHours(-24)} -EA SilentlyContinue).Count}catch{}
# Rev 15: oldest retained Security event — patient_zero.py uses it to tell a
# retention boundary from a true origin.
$oldest=$null
try{$e=Get-WinEvent -LogName Security -Oldest -MaxEvents 1 -EA SilentlyContinue;if($e){$oldest=$e.TimeCreated.ToUniversalTime().ToString('o')}}catch{}
[pscustomobject]@{skill='attest';host=$env:COMPUTERNAME;utc=$now.ToString('o');alive=$true;last_boot=$boot.ToString('o');track=$Track;admin_failed_60s=$failed;admin_ok_5min=$ok;local_admin_count=$lac;sys_remote_conns=$sysconn;sysmon_status=$sysmon;raw_4624_24h=$raw4624;oldest_security_event=$oldest;blind_check=$blind;blind_count=$blindCount}|ConvertTo-Json -Compress
