# un_isolate_host — undo for isolate_host (Rev 17; Rev 20 target contract).
#
# The isolate payload journaled: previous_default_inbound (per profile) and
# the names of the allow rules it disabled. This undo restores that state.
#
# REV 20: the engine's undo path now passes $Target as a JSON document
# {"rules": [...], "defaults": "<previous_default_inbound JSON>"} captured
# from the journal entry (plain 'host' still accepted — it restores nothing
# mechanical and says so honestly).
$ErrorActionPreference = 'Stop'
try {
  $rules = @()
  $defaultsJson = ''
  if ($Target -and $Target.Trim().StartsWith('{')) {
    $doc = $Target | ConvertFrom-Json
    $rules = @($doc.rules | ForEach-Object { [string]$_ } | Where-Object { $_ })
    $defaultsJson = [string]$doc.defaults
  } elseif ($Target -and $Target -ne 'host') {
    # legacy comma-joined names
    $rules = @($Target -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  }

  $restored = 0
  foreach ($n in $rules) {
    Enable-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue
    $restored++
  }

  # restore each profile's DefaultInboundAction from the journaled map
  $defaultsRestored = 0
  if ($defaultsJson) {
    try {
      $prev = $defaultsJson | ConvertFrom-Json
      foreach ($p in $prev.PSObject.Properties) {
        if ($p.Value -and $p.Value -ne 'Block') {
          Set-NetFirewallProfile -Profile $p.Name -DefaultInboundAction $p.Value -ErrorAction SilentlyContinue
          $defaultsRestored++
        }
      }
    } catch { $defaultsJson = "unparseable: $defaultsJson" }
  }

  # remove our WinRM allow rule (it exists only during isolation)
  Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue

  $nowDefault = @{}
  foreach ($p in (Get-NetFirewallProfile)) { $nowDefault[$p.Name] = [string]$p.DefaultInboundAction }
  $winrmGone = -not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)

  [pscustomobject]@{
    ok=$true; action='un_isolate_host'; host=$env:COMPUTERNAME
    reenabled_rules=$restored
    defaults_restored=$defaultsRestored
    winrm_rule_removed=$winrmGone
    now_default_inbound=($nowDefault | ConvertTo-Json -Compress)
    note='restored journaled allow rules and profile defaults; check the journal for anything this could not restore mechanically'
  } | ConvertTo-Json -Compress -Depth 4
} catch {
  [pscustomobject]@{ok=$false; action='un_isolate_host'; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
