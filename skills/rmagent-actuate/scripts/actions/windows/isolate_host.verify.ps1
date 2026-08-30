# verify: isolate_host — the block rule must exist and all profiles must be on.
$r = Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-BlockInbound' -ErrorAction SilentlyContinue
$p = @(Get-NetFirewallProfile | Where-Object { $_.Enabled -eq $true })
if ($r -and $p.Count -ge 3) { 'VERIFIED' } else { 'NOT-VERIFIED' }