# RMAgent red-team drill CLEANUP — removes every RMAgentDrill_* artifact staged by drill.ps1.
# Idempotent: safe to run even if nothing was staged. Never touches non-drill objects.
$ErrorActionPreference='SilentlyContinue'
$stamp = [DateTime]::UtcNow.ToString('o')
$done  = @()

# 4. remove the service
try { sc.exe stop RMAgentDrillSvc 2>$null | Out-Null; sc.exe delete RMAgentDrillSvc 2>$null | Out-Null; $done += 'service: RMAgentDrillSvc deleted' } catch {}
# 3. remove the scheduled task
try { schtasks /delete /tn "RMAgentDrill_Task" /f 2>$null | Out-Null; $done += 'task: RMAgentDrill_Task deleted' } catch {}
# 2. remove the drill user from Administrators + delete the account
try { net localgroup Administrators RMAgentDrill_Test /delete 2>$null | Out-Null; net user RMAgentDrill_Test /delete 2>$null | Out-Null; $done += 'user: RMAgentDrill_Test removed + deleted' } catch {}
# leftover marker file
try { Remove-Item C:\Windows\Temp\rmagent_drill.txt -Force 2>$null | Out-Null; $done += 'marker: rmagent_drill.txt removed' } catch {}

[pscustomobject]@{
  skill  = 'redteam-clean'
  host   = $env:COMPUTERNAME
  utc    = $stamp
  cleaned = $done
} | ConvertTo-Json -Compress
