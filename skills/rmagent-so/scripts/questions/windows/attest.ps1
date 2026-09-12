# attest — digest + blind_check + domain_role. TargetUserName only.
# sys_remote_conns lives on edges (budget).
function MT($e){$t=$e.Properties[1].Value;if($t -is [string]){return $Track -contains (($t -split '\\')[-1])};return $false}
$now=[DateTime]::UtcNow;$boot=(gcim Win32_OperatingSystem).LastBootUpTime
$role='wg';$dom='';try{$cs=gcim Win32_ComputerSystem;if($cs.PartOfDomain){$role=$(if($cs.DomainRole -ge 4){'dc'}else{'member'});$dom=$cs.Domain}else{$dom=$cs.Workgroup}}catch{}
$failed=0;$ok=0;try{$failed=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$now.AddSeconds(-60)}|? MT).Count}catch{};try{$ok=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddMinutes(-5)}|? MT).Count}catch{}
$lac=0;try{$lac=@(Get-LocalGroupMember -Group Administrators).Count}catch{}
$sysmon='?';try{$svc=Get-Service Sysmon64,Sysmon|Select -First 1;if($svc){$sysmon="$($svc.Name)=$($svc.Status)"}else{$sysmon='none'}}catch{}
$want=@{'0CCE9215'='Logon';'0CCE9216'='Logoff';'0CCE921B'='Special Logon';'0CCE921C'='Other Logon/Logoff';'0CCE9217'='Account Lockout'};$blind=@{}
try{$csv=auditpol /get /category:* /r 2>$null|Out-String -Width 400;foreach($l in ($csv -split "`n")){$p=$l -split ',';for($i=0;$i -lt $p.Count-1;$i++){if($p[$i] -match '\{(0CCE\w{4})'){$k=$Matches[1];if($want.ContainsKey($k)){$blind[$want[$k]]=$(if($p[$i+1] -match 'Success'){'ok'}else{'BLIND'})}}}}}catch{}
foreach($w in $want.Values){if(-not $blind.ContainsKey($w)){$blind[$w]='?'}}
try{$blind['ProcCL']=$(if((gp HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit ProcessCreationIncludeCmdLine_Enabled).ProcessCreationIncludeCmdLine_Enabled -eq 1){'ok'}else{'BLIND'})}catch{$blind['ProcCL']='?'}
try{$blind['SBL']=$(if((gp HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging EnableScriptBlockLogging).EnableScriptBlockLogging -eq 1){'ok'}else{'BLIND'})}catch{$blind['SBL']='?'}
$blindCount=@($blind.Values|?{$_ -like 'BLIND*'}).Count
# Rev 21: on a DC, the domain-level questions (krb/dcsync/dirchange) depend on
# Kerberos + Directory Service Access auditing. On a member/workgroup box those
# events do not exist at all — record that honestly so a member server never
# pretends "no DCSync" is a clean answer.
if($role -eq 'dc'){
  try{$blind['DC-Audit']=$(if((auditpol /get /subcategory:'{0CCE923F-69AE-11D9-BED3-505054503030}' /r 2>$null|Out-String) -match 'Success'){'ok'}else{'BLIND'})}catch{$blind['DC-Audit']='?'}
  $blindCount=@($blind.Values|?{$_ -like 'BLIND*'}).Count
}
$raw4624=0;try{$raw4624=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddHours(-24)}).Count}catch{}
$oldest=$null;try{$e=Get-WinEvent -LogName Security -Oldest -MaxEvents 1;if($e){$oldest=$e.TimeCreated.ToUniversalTime().ToString('o')}}catch{}
[pscustomobject]@{skill='attest';host=$env:COMPUTERNAME;utc=$now.ToString('o');alive=$true;last_boot=$boot.ToString('o');track=$Track;domain_role=$role;domain=$dom;admin_failed_60s=$failed;admin_ok_5min=$ok;local_admin_count=$lac;sysmon_status=$sysmon;raw_4624_24h=$raw4624;oldest_security_event=$oldest;blind_check=$blind;blind_count=$blindCount}|ConvertTo-Json -Compress
