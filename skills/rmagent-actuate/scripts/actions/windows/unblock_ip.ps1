# unblock_ip - remove an RMAgent block_ip rule. Engine injects $Target (the IP).
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $rule = "RMAgent-Block-$Target"
  $r = Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue
  if ($r) {
    Remove-NetFirewallRule -DisplayName $rule -ErrorAction Stop
    $gone = -not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)
    [pscustomobject]@{ action='unblock_ip'; ip=$Target; rule=$rule;
                      status= if($gone){'removed'}else{'failed'} } | ConvertTo-Json -Compress
  } else {
    [pscustomobject]@{ action='unblock_ip'; ip=$Target; rule=$rule; status='not-found' } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='unblock_ip'; ip=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
