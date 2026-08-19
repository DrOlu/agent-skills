# block_ip.verify — confirm the firewall rule exists and is enabled. Engine injects $Target.
$rule = "RMAgent-Block-$Target"
$r = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
if ($r -and $r.Enabled -eq 'True') { 'VERIFIED' } else { 'NOT_VERIFIED' }
