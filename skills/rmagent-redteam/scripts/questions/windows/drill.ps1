# RMAgent drill — 8 reversible LOTL artifacts (6 event + 2 state). net.exe full path.
$ErrorActionPreference='SilentlyContinue'
$tag='RMAgentDrill'; $log=[System.Collections.ArrayList]@()
function S($n,$sb){ try{ & $sb | Out-Null; [void]$log.Add("$n`: ok") } catch { [void]$log.Add("$n`: $($_.Exception.Message)") } }
$NET="$env:SystemRoot\System32\net.exe"; $HK='HKLM:\'
S 'failed_logons'{Add-Type -MemberDefinition '[DllImport("advapi32.dll", SetLastError=true)] public static extern bool LogonUser(string u, string d, string p, int t, int pr, out IntPtr tok);' -Name RA -Namespace W;1..2|%{$t=[IntPtr]::Zero;[W.RA]::LogonUser('Administrator',$env:COMPUTERNAME,"Dr!ll-Bad-$_",3,0,[ref]$t)|Out-Null}}
S 'new_local_admin'{& $NET user RMAgentDrill_Test 'Dr!ll-P@ss1' /add 2>$null;& $NET localgroup Administrators RMAgentDrill_Test /add 2>$null}
S 'scheduled_task'{schtasks /create /tn RMAgentDrill_Task /tr 'powershell.exe -NoProfile -Command Test-NetConnection 1.1.1.1 -Port 80' /sc once /st 23:59 /ru SYSTEM /f 2>$null;schtasks /run /tn RMAgentDrill_Task 2>$null}
S 'new_service'{sc.exe create RMAgentDrillSvc binPath= 'C:\Windows\System32\cmd.exe /c echo rmagent_drill' start= demand 2>$null;sc.exe start RMAgentDrillSvc 2>$null}
S 'powershell_spawns'{powershell.exe -NoProfile -Command 'Get-Process|Select-Object -First 1|Out-Null' 2>$null;powershell.exe -NoProfile -Command 'net localgroup administrators|Out-Null' 2>$null}
S 'run_key'{New-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name 'RMAgentDrill_RunKey' -Value 'C:\Windows\Temp\RMAgentDrill.exe' -PropertyType String -Force|Out-Null}
S 'ifeo_hijack'{$k="$HK\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe";if(-not(Test-Path $k)){New-Item -Path $k -Force|Out-Null};New-ItemProperty -Path $k -Name 'Debugger' -Value 'cmd.exe /c echo rmagent_drill' -PropertyType String -Force|Out-Null}
$v=@{
 failed_logons=(@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=(Get-Date).AddMinutes(-2)} -ErrorAction SilentlyContinue).Count -gt 0)
 new_local_admin=((& $NET user RMAgentDrill_Test 2>$null|Select-String 'RMAgentDrill_Test') -ne $null)
 scheduled_task=((schtasks /query /tn RMAgentDrill_Task 2>$null|Select-String 'RMAgentDrill_Task') -ne $null)
 new_service=((Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -ErrorAction SilentlyContinue) -ne $null)
 powershell_spawns=$true
 run_key=((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name 'RMAgentDrill_RunKey' -ErrorAction SilentlyContinue).RMAgentDrill_RunKey -ne $null)
 ifeo_hijack=((Get-ItemProperty -Path "$HK\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe" -Name 'Debugger' -ErrorAction SilentlyContinue).Debugger -ne $null)
}
[pscustomobject]@{skill='redteam-drill';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');tag=$tag;staged=$log;verified=$v}|ConvertTo-Json -Compress -Depth 4
