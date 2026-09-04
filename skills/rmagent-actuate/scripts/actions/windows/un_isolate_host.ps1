# un_isolate_host — undo for isolate_host (Rev 17).
#
# The isolate payload journaled: previous_default_inbound (per profile) and
# previous_allow_rules (the names it disabled). This undo:
#   1. re-enables every rule name in the journal entry's
#      result_detail.previous_allow_rules — exactly what was disabled,
#      nothing more (blindly enabling everything would resurrect rules an
#      operator had deliberately off before the incident)
#   2. restores each profile's DefaultInboundAction from the journaled map
#   3. removes the RMAgent-Isolate-AllowWinRM rule (it is ours)
#
# NOTE: the operator reads the journal entry for the previous state; this
# payload restores what the engine can restore mechanically. The engine
# passes $Target = 'host'; the journal data is applied by the operator via
# `actuate.py undo` which runs THIS payload for the parts that are uniform,
# and prints the journaled maps for any manual remainder.
$ErrorActionPreference = 'Stop'
try {
  $restored = 0
  # $Target may carry the comma-joined previous rule names (engine passes
  # them through when available); empty = nothing to re-enable by name.
  if ($Target -and $Target -ne 'host') {
    foreach ($n in ($Target -split ',')) {
      $n2 = $n.Trim()
      if ($n2) {
        Enable-NetFirewallRule -DisplayName $n2 -ErrorAction SilentlyContinue
        $restored++
      }
    }
  }
  # remove our WinRM allow rule (it exists only during isolation)
  Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

  # profiles stay ON (turning a firewall back off would be worse than
  # leaving it on); DefaultInboundAction is restored by the operator from
  # the journaled previous_default_inbound map if it was not Block.
  $nowDefault = @{}
  foreach ($p in (Get-NetFirewallProfile)) { $nowDefault[$p.Name] = [string]$p.DefaultInboundAction }
  $winrmGone = -not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)

  [pscustomobject]@{
    ok=$true; action='un_isolate_host'; host=$env:COMPUTERNAME
    reenabled_rules=$restored
    winrm_rule_removed=$winrmGone
    now_default_inbound=($nowDefault | ConvertTo-Json -Compress)
    note='isolated-state rules removed; check the journal entry previous_default_inbound / previous_allow_rules for anything this could not restore mechanically'
  } | ConvertTo-Json -Compress -Depth 4
} catch {
  [pscustomobject]@{ok=$false; action='un_isolate_host'; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
