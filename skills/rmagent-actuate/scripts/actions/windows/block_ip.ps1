# block_ip — Windows Firewall deny rule for a source IP. Engine injects $Target.
# Creates rule "RMAgent-Block-<ip>" (deny, inbound, any port/protocol). Idempotent.
$rule = "RMAgent-Block-$Target"
$existing = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
if ($existing) {
  [pscustomobject]@{ action='block_ip'; ip=$Target; rule=$rule; status='already-exists' } | ConvertTo-Json -Compress
} else {
  New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Block `
    -RemoteAddress $Target -Profile Any | Out-Null
  [pscustomobject]@{ action='block_ip'; ip=$Target; rule=$rule; status='created' } | ConvertTo-Json -Compress
}
