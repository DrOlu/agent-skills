# unblock_ip — remove an RMAgent block_ip rule. Engine injects $Target (the IP).
$rule = "RMAgent-Block-$Target"
$r = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
if ($r) {
  Remove-NetFirewallRule -DisplayName $rule
  [pscustomobject]@{ action='unblock_ip'; ip=$Target; rule=$rule; status='removed' } | ConvertTo-Json -Compress
} else {
  [pscustomobject]@{ action='unblock_ip'; ip=$Target; rule=$rule; status='not-found' } | ConvertTo-Json -Compress
}
