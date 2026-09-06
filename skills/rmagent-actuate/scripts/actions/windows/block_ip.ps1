# block_ip - Windows Firewall deny rule for a source IP. Engine injects $Target.
# Creates rule "RMAgent-Block-<ip>" (deny, inbound, any port/protocol). Idempotent.
# REV 17 (C4): Stop + observe - the status reports what the box actually has
# after the mutation, not what we asked for.
$ErrorActionPreference = 'Stop'
try {
  $rule = "RMAgent-Block-$Target"
  $existing = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
  if ($existing) {
    [pscustomobject]@{ action='block_ip'; ip=$Target; rule=$rule; status='already-exists' } | ConvertTo-Json -Compress
  } else {
    New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Block `
      -RemoteAddress $Target -Profile Any | Out-Null
    # observe: is the rule REALLY there?
    $now = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
    [pscustomobject]@{ action='block_ip'; ip=$Target; rule=$rule;
                       status= if($now){'created'}else{'failed'} } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='block_ip'; ip=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
