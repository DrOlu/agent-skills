# verify: isolate_host — profile defaults must be Block and the WinRM rule present.
$defaults = @(Get-NetFirewallProfile | ForEach-Object { [string]$_.DefaultInboundAction })
$winrm = Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue
if (($defaults | Where-Object { $_ -ne 'Block' }).Count -eq 0 -and $winrm) { 'VERIFIED' } else { 'NOT_VERIFIED' }
