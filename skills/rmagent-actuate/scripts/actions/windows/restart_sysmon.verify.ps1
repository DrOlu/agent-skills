# restart_sysmon.verify - service running AND the EID3 hook actually records a
# connection (the same live experiment that proved it was dark).
$svc = Get-Service Sysmon64 -ErrorAction SilentlyContinue
if (-not $svc -or $svc.Status -ne 'Running') { 'NOT_VERIFIED'; exit }
try {
  $c = New-Object Net.Sockets.TcpClient
  $c.Connect('52.3.242.251', 4222)   # estate mesh peer - known-safe probe
  Start-Sleep -Seconds 3
  $c.Close()
} catch {}
Start-Sleep -Seconds 2
$since = (Get-Date).AddMinutes(-2)
try { $n = @(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational';Id=3;StartTime=$since}).Count } catch { $n = 0 }
if ($n -gt 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
