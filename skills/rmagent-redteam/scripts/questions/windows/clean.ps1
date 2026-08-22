# RMAgent red-team drill CLEANUP — removes every RMAgentDrill_* artifact staged by drill.ps1.
# Idempotent: safe to run even if nothing was staged. Never touches non-drill objects.
# BUG FIX (2026-08-19): net.exe by FULL PATH — Impacket's net.py shadows `net` on ws1.
# REV 5 (2026-08-22): +run_key +ifeo_hijack removal (the state-based artifacts).
$ErrorActionPreference='SilentlyContinue'
$stamp = [DateTime]::UtcNow.ToString('o')
$done  = @()
$NET   = "$env:SystemRoot\System32\net.exe"

# service
try { sc.exe stop RMAgentDrillSvc 2>$null | Out-Null; sc.exe delete RMAgentDrillSvc 2>$null | Out-Null; $done += 'service: RMAgentDrillSvc deleted' } catch {}
# scheduled task
try { schtasks /delete /tn "RMAgentDrill_Task" /f 2>$null | Out-Null; $done += 'task: RMAgentDrill_Task deleted' } catch {}
# drill user (full-path net.exe)
try { & $NET localgroup Administrators RMAgentDrill_Test /delete 2>$null | Out-Null; & $NET user RMAgentDrill_Test /delete 2>$null | Out-Null; $done += 'user: RMAgentDrill_Test removed + deleted' } catch {}
# run key (T1547.001)
try { Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'RMAgentDrill_RunKey' -Force 2>$null; $done += 'run_key: RMAgentDrill_RunKey removed' } catch {}
# IFEO debugger (T1546.010)
try { Remove-Item -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe' -Recurse -Force 2>$null; $done += 'ifeo: RMAgentDrill.exe IFEO key removed' } catch {}
# leftover marker file
try { Remove-Item C:\Windows\Temp\rmagent_drill.txt -Force 2>$null | Out-Null; $done += 'marker: rmagent_drill.txt removed' } catch {}

# --- VERIFY cleanup actually landed (so we can't report a false "cleaned") ---
$still = @()
if (Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -ErrorAction SilentlyContinue) { $still += 'service' }
if (schtasks /query /tn RMAgentDrill_Task 2>$null | Select-String 'RMAgentDrill_Task') { $still += 'task' }
if ((& $NET user RMAgentDrill_Test 2>$null | Select-String 'RMAgentDrill_Test')) { $still += 'user' }
if ((Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'RMAgentDrill' })) { $still += 'admin-member' }
if ((Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'RMAgentDrill_RunKey' -ErrorAction SilentlyContinue).RMAgentDrill_RunKey) { $still += 'run_key' }
if ((Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\RMAgentDrill.exe' -Name 'Debugger' -ErrorAction SilentlyContinue).Debugger) { $still += 'ifeo' }

[pscustomobject]@{
  skill        = 'redteam-clean'
  host         = $env:COMPUTERNAME
  utc          = $stamp
  cleaned      = $done
  still_present = $still
} | ConvertTo-Json -Compress -Depth 3
