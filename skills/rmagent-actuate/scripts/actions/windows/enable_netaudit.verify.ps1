# enable_netaudit.verify - one live connection must produce Security 5156.
$probe = {
  try {
    $c = New-Object Net.Sockets.TcpClient
    $c.Connect('52.3.242.251', 4222)   # estate mesh peer - known-safe probe
    Start-Sleep -Seconds 3
    $c.Close()
  } catch {}
}
& $probe
Start-Sleep -Seconds 2
$since = (Get-Date).AddMinutes(-2)
$n = 0
try { $n = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=5156; StartTime=$since}).Count } catch {}
if ($n -gt 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
