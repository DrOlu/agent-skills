# RMAgent verify — report which drill artifacts are CURRENTLY present.
# READ-ONLY: stages nothing, removes nothing. Used by `detect` mode to score
# rmagent against whatever is already on the box (e.g. staged earlier with
# `stage --keep`, possibly hours ago).
#
# TWO KINDS OF SIGNAL, checked differently — a bug in the first version:
#   STATEFUL artifacts (user/task/service/run-key/IFEO/marker) are reliable to
#     check any time later: they persist until cleaned.
#   EVENT signals (failed logons, PowerShell spawns) are TIME-BOUND. The first
#     version checked "any 4625/4688 in 24h", which is ALWAYS true on a live
#     box (WinRM itself spawns PowerShell; real attackers leave 4625s) — so a
#     cleaned estate still reported them present. Now they are bounded to the
#     SAME 1h window the hunt scores, and matched drill-specifically:
#     - failed_logons: 4625 for Administrator from a LOCAL/blank source (the
#       drill's LogonUser runs on the box itself; a real attacker's 4625s
#       carry an external IpAddress and do not count)
#     - powershell_spawns: 4688 whose command line matches the drill's
#       distinctive 'localgroup' spawn
#   Consequence, stated honestly: for a DELAYED detect (>1h after stage) the
#   event signals report not-present — correct, because the hunt's 1h window
#   cannot see them either. Only the stateful artifacts are scoreable late.
$ErrorActionPreference='SilentlyContinue'
$NET="$env:SystemRoot\System32\net.exe"; $HK='HKLM:\'
$win=(Get-Date).AddHours(-1)   # same window the hunt scores

# --- stateful artifacts: reliable any time later ---
$admin = (& $NET user RMAgentDrill_Test 2>$null|Select-String 'RMAgentDrill_Test') -ne $null
$task  = (schtasks /query /tn RMAgentDrill_Task 2>$null|Select-String 'RMAgentDrill_Task') -ne $null
$svc   = (Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -ErrorAction SilentlyContinue) -ne $null
$rk    = (Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name 'RMAgentDrill_RunKey' -ErrorAction SilentlyContinue).RMAgentDrill_RunKey -ne $null
$ifeo  = (Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe" -Name 'Debugger' -ErrorAction SilentlyContinue).Debugger -ne $null
$mark  = Test-Path "$env:TEMP\rmagent_drill.txt"

# --- event signals: 1h window, drill-specific matchers (see header) ---
$fl=$false
try{
  Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$win} -ErrorAction SilentlyContinue | ForEach-Object {
    $x=[xml]$_.ToXml(); $d=@{}
    foreach($i in $x.Event.EventData.Data){ $d[$i.Name]=$i.'#text' }
    $u=$d['TargetUserName']; $ip=$d['IpAddress']
    if($u -like 'Administrator*' -and ($ip -eq '-' -or $ip -eq '' -or $ip -eq '127.0.0.1' -or $ip -eq '::1')){ $fl=$true }
  }
}catch{}
$ps=$false
try{
  $ps = @(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=$win} -ErrorAction SilentlyContinue |
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