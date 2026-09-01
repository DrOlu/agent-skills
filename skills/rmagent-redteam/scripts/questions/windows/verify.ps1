# RMAgent verify — which drill artifacts are CURRENTLY present? READ-ONLY.
# Stateful artifacts (user/task/service/run-key/IFEO/marker) persist until
# cleaned — reliable any time later. Event signals are TIME-BOUND: bounded to
# the same 1h window the hunt scores, matched drill-specifically (4625 for
# Administrator from a local/blank source; 4688 with 'localgroup' in the
# cmdline). Delayed detect (>1h) correctly reports events not-present.
$ErrorActionPreference='SilentlyContinue'
$NET="$env:SystemRoot\System32\net.exe"; $HK='HKLM:\'
$win=(Get-Date).AddHours(-1)
$admin = ((& $NET user RMAgentDrill_Test 2>$null|Select-String 'RMAgentDrill_Test') -ne $null)
$task  = ((schtasks /query /tn RMAgentDrill_Task 2>$null|Select-String 'RMAgentDrill_Task') -ne $null)
$svc   = ((Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -EA SilentlyContinue) -ne $null)
$rk    = ((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name 'RMAgentDrill_RunKey' -EA SilentlyContinue).RMAgentDrill_RunKey -ne $null)
$ifeo  = ((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe" -Name 'Debugger' -EA SilentlyContinue).Debugger -ne $null)
$mark  = (Test-Path "$env:TEMP\rmagent_drill.txt")
$fl=$false
try{
  Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$win} -EA SilentlyContinue | ForEach-Object {
    $x=[xml]$_.ToXml(); $d=@{}
    foreach($i in $x.Event.EventData.Data){ $d[$i.Name]=$i.'#text' }
    $u=$d['TargetUserName']; $ip=$d['IpAddress']
    if($u -like 'Administrator*' -and ($ip -eq '-' -or $ip -eq '' -or $ip -eq '127.0.0.1' -or $ip -eq '::1')){ $fl=$true }
  }
}catch{}
$ps=$false
try{
  $ps = @(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=$win} -EA SilentlyContinue |
    Where-Object { ($_.Message+'') -match 'localgroup' }).Count -gt 0
}catch{}
$v=@{
 failed_logons=$fl
 new_local_admin=$admin
 scheduled_task=$task
 new_service=$svc
 powershell_spawns=$ps
 run_key=$rk
 ifeo_hijack=$ifeo
 marker=$mark
}
[pscustomobject]@{skill='redteam-verify';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');present=$v}|ConvertTo-Json -Compress -Depth 4