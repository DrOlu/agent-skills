# un_isolate_host — undo for isolate_host. Removes the RMAgent isolation
# rules. Does NOT restore previous profile Enabled states automatically —
# the operator reads previous_profiles from the journal entry and decides
# (blindly re-disabling a firewall profile is worse than leaving it on).
try {
  Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-BlockInbound','RMAgent-Isolate-AllowEstablished','RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
  [pscustomobject]@{ok=$true; action='un_isolate_host'; removed=$true
    note='isolation rules removed; check journal previous_profiles if you need the old profile states'} |
    ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}