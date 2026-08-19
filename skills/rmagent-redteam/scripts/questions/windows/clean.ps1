# RMAgent red-team drill CLEANUP — removes every RMAgentDrill_* artifact staged by drill.ps1.
# Idempotent: safe to run even if nothing was staged. Never touches non-drill objects.
# BUG FIX (2026-08-19): net.exe by FULL PATH — Impacket's net.py shadows `net` on ws1,
# so the old `net localgroup ... /delete` silently failed there.
$ErrorActionPreference='SilentlyContinue'
$stamp = [DateTime]::UtcNow.ToString('o')
$done  = @()
$NET   = "$env:SystemRoot\System32\net.exe"

# 4. remove the service
try { sc.exe stop RMAgentDrillSvc 2>$null | Out-Null; sc.exe delete RMAgentDrillSvc 2>$null | Out-Null; $done += 'service: RMAgentDrillSvc deleted' } catch {}
# 3. remove the scheduled task
try { schtasks /delete /tn "RMAgentDrill_Task" /f 2>$null | Out-Null; $done += 'task: RMAgentDrill_Task deleted' } catch {}
# 2. remove the drill user from Administrators + delete the account (full-path net.exe)
try { & $NET localgroup Administrators RMAgentDrill_Test /delete 2>$null | Out-Null; & $NET user RMAgentDrill_Test /delete 2>$null | Out-Null; $done += 'user: RMAgentDrill_Test removed + deleted' } catch {}
# leftover marker file
try { Remove-Item C:\Windows\Temp\rmagent_drill.txt -Force 2>$null | Out-Null; $done += 'marker: rmagent_drill.txt removed' } catch {}

# --- VERIFY cleanup actually landed (so we can't report a false "cleaned") ---
$still = @()
if (Get-CimInstance Win32_Service -Filter "Name='RMAgentDrillSvc'" -ErrorAction SilentlyContinue) { $still += 'service' }
if (schtasks /query /tn RMAgentDrill_Task 2>$null | Select-String 'RMAgentDrill_Task') { $still += 'task' }
if ((& $NET user RMAgentDrill_Test 2>$null | Select-String 'RMAgentDrill_Test')) { $still += 'user' }
if ((Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'RMAgentDrill' })) { $still += 'admin-member' }

[pscustomobject]@{
  skill        = 'redteam-clean'
  host         = $env:COMPUTERNAME
  utc          = $stamp
  cleaned      = $done
  still_present = $still
} | ConvertTo-Json -Compress -Depth 3
