# verify: un_isolate_host — the isolation rules must be GONE.
$r = Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-BlockInbound' -ErrorAction SilentlyContinue
if (-not $r) { 'VERIFIED' } else { 'NOT-VERIFIED' }