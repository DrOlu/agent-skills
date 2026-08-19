# unblock_ip.verify — confirm the rule is gone. Engine injects $Target.
$rule = "RMAgent-Block-$Target"
$r = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
if (-not $r) { 'VERIFIED' } else { 'NOT_VERIFIED' }
