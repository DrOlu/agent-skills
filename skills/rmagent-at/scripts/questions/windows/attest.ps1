# attest — alive + Administrator/SYSTEM smoke + blind check + log edge. Digest only.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList
# Match-TargetTrack matches ONLY TargetUserName (not SubjectUserName) so a
# SYSTEM service touching a user doesn't light up as "admin activity".
function MT($e){$t=$e.Properties[1].Value;if($t -is [string]){return $Track -contains (($t -split '\\')[-1])};return $false}
$now=[DateTime]::UtcNow
$boot=(gcim Win32_OperatingSystem).LastBootUpTime
$failed=0;$ok=0
try{$failed=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$now.AddSeconds(-60)}|? MT).Count}catch{}
try{$ok=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddMinutes(-5)}|? MT).Count}catch{}
$lac=0
try{$lac=@(Get-LocalGroupMember -Group Administrators).Count}catch{}
# SYSTEM/tracked-owned processes with an ESTABLISHED remote connection.
# Invoke-CimMethod (not .GetOwner().User, which returns '' on 2022 via WinRM).
$sysconn=0
try{$op=@(Get-CimInstance Win32_Process|%{$u=(Invoke-CimMethod -InputObject $_ -MethodName GetOwner).User;if($u -and ($Track -contains ($u -split '\\')[-1])){$_.ProcessId}});$sysconn=@(Get-NetTCPConnection -State Established|?{$_.RemoteAddress -notmatch '^(127\.|0\.|::)' -and $op -contains $_.OwningProcess}|gu RemoteAddress).Count}catch{}
# Sysmon health — the tripwire that says when to fall back to kernring.
$sysmon='unknown'
try{$svc=Get-Service Sysmon64,Sysmon|Select -First 1;if($svc){$sysmon="$($svc.Name)=$($svc.Status)"}else{$sysmon='not-installed'}}catch{}
# blind_check — can this witness actually SEE? (WS2 was blind: Logon audit
# Failure-only → edges returned ZERO logons while connected.)
# REV 17 (H5): locale-invariant blind_check. The CSV from `auditpol /r`
# carries a Subcategory GUID column — we locate the GUID cell (starts with
# {0CCE) and read the NEXT column (Inclusion Setting), so neither the display
# language nor a column-order change can fake 'sighted'. GUIDs verified live
# on WS1 2026-09-03 (the first cut had two mappings from memory — wrong).
# Plus two new sources the questions depend on: 4688 command-line inclusion
# and 4104 script-block logging — the two an attacker is most likely to
# switch off.
$want=@{'0CCE9215'='Logon';'0CCE9216'='Logoff';'0CCE921B'='Special Logon';'0CCE921C'='Other Logon/Logoff';'0CCE9217'='Account Lockout'}
$blind=@{}
try{
  $csv = auditpol /get /category:* /r 2>$null | Out-String -Width 400
  foreach($l in ($csv -split "`n")){
    $p = $l -split ','
    for($i=0; $i -lt $p.Count-1; $i++){
      if($p[$i] -match '\{(0CCE\w{4})'){
        $k = $Matches[1]
        if($want.ContainsKey($k)){
          $inc = $p[$i+1]
          $blind[$want[$k]] = $(if($inc -match 'Success'){'ok'}else{'BLIND'})
        }
      }
    }
  }
}catch{}
foreach($w in $want.Values){if(-not $blind.ContainsKey($w)){$blind[$w]='unknown'}}
foreach($kv in @(@('Process CmdLine','HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit','ProcessCreationIncludeCmdLine_Enabled'),@('ScriptBlock Logging','HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging','EnableScriptBlockLogging'))){try{$blind[$kv[0]]=$(if((gp $kv[1] $kv[2]).$($kv[2]) -eq 1){'ok'}else{'BLIND'})}catch{$blind[$kv[0]]='unknown'}}
$blindCount=@($blind.Values|?{$_ -like 'BLIND*'}).Count
$raw4624=0
try{$raw4624=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$now.AddHours(-24)}).Count}catch{}
# Rev 15: oldest retained Security event — patient_zero.py uses it to tell a
# retention boundary from a true origin.
$oldest=$null
try{$e=Get-WinEvent -LogName Security -Oldest -MaxEvents 1;if($e){$oldest=$e.TimeCreated.ToUniversalTime().ToString('o')}}catch{}
[pscustomobject]@{skill='attest';host=$env:COMPUTERNAME;utc=$now.ToString('o');alive=$true;last_boot=$boot.ToString('o');track=$Track;admin_failed_60s=$failed;admin_ok_5min=$ok;local_admin_count=$lac;sys_remote_conns=$sysconn;sysmon_status=$sysmon;raw_4624_24h=$raw4624;oldest_security_event=$oldest;blind_check=$blind;blind_count=$blindCount}|ConvertTo-Json -Compress
