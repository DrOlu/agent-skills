# RMAgent verify — report which drill artifacts are CURRENTLY present.
# READ-ONLY: stages nothing, removes nothing. Used by `detect` mode to score
# rmagent against whatever is already on the box (e.g. staged earlier with
# `stage --keep`, possibly hours ago).
# The verification checks are identical to drill.ps1's `verified` block.
$ErrorActionPreference='SilentlyContinue'
$NET="$env:SystemRoot\System32\net.exe"; $HK='HKLM:\'
$v=@{
 failed_logons=(@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue).Count -gt 0)
 new_local_admin=((& $NET user RMAgentDrill_Test 2>$null|Select-String 'RMAgentDrill_Test') -ne $null)
 scheduled_task=((schtasks /query /tn RMAgentDrill_Task 2>$null|Select-String 'RMAgentDrill_Task') -ne $null)
 new_service=((Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -ErrorAction SilentlyContinue) -ne $null)
 powershell_spawns=(@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=(Get-Date).AddHours(-24)} -ErrorAction SilentlyContinue|?{($_.Message+'') -match 'powershell'}).Count -gt 0)
 run_key=((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name 'RMAgentDrill_RunKey' -ErrorAction SilentlyContinue).RMAgentDrill_RunKey -ne $null)
 ifeo_hijack=((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe" -Name 'Debugger' -ErrorAction SilentlyContinue).Debugger -ne $null)
}
[pscustomobject]@{skill='redteam-verify';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');present=$v}|ConvertTo-Json -Compress -Depth 4