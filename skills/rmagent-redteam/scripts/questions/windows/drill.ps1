# RMAgent drill — stages reversible LOTL artifacts. Benign. RMAgentDrill_* prefixed.
# Signals (and the rmagent field that should fire): 4625 admin-failed (attest/sketch),
# 4720+4732 new-local-admin (explain.identity_changes/sketch.new_local_admins),
# 4698 task (explain.task_events/sketch.new_tasks), 7045 service (explain.service_events),
# 4688 powershell spawns (explain.proc_spawns), SYSTEM outbound conn (edges.conns).
# Compact form keeps the base64-encoded WinRM command under the ~8191-char cmdline cap.
$ErrorActionPreference='SilentlyContinue'
$tag='RMAgentDrill'; $log=[System.Collections.ArrayList]@()
function S($n,$sb){ try{ & $sb | Out-Null; [void]$log.Add("$n`: ok") } catch { [void]$log.Add("$n`: $($_.Exception.Message)") } }

S 'failed_logons'    { for($i=0;$i -lt 2;$i++){ net use "\\$env:COMPUTERNAME\IPC$" /user:Administrator "Drill-Bad-$i" 2>$null }; net use "\\$env:COMPUTERNAME\IPC$" /delete 2>$null }
S 'new_local_admin'  { net user RMAgentDrill_Test 'Dr!ll-P@ss1' /add 2>$null; net localgroup Administrators RMAgentDrill_Test /add 2>$null }
S 'scheduled_task'   { schtasks /create /tn RMAgentDrill_Task /tr 'powershell.exe -NoProfile -Command Test-NetConnection 1.1.1.1 -Port 80 -WarningAction SilentlyContinue' /sc once /st 23:59 /ru SYSTEM /f 2>$null; schtasks /run /tn RMAgentDrill_Task 2>$null }
S 'new_service'      { sc.exe create RMAgentDrillSvc binPath= 'C:\Windows\System32\cmd.exe /c echo rmagent_drill' start= demand 2>$null; sc.exe start RMAgentDrillSvc 2>$null }
S 'powershell_spawns'{ powershell.exe -NoProfile -Command 'Get-Process|Select-Object -First 1|Out-Null' 2>$null; powershell.exe -NoProfile -Command 'net localgroup administrators|Out-Null' 2>$null }

[pscustomobject]@{ skill='redteam-drill'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o'); tag=$tag; staged=$log } | ConvertTo-Json -Compress -Depth 3
