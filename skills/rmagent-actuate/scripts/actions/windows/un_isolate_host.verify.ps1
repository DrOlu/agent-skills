# verify: un_isolate_host — the RMAgent WinRM allow rule must be gone.
if (-not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)) { 'VERIFIED' } else { 'NOT_VERIFIED' }
