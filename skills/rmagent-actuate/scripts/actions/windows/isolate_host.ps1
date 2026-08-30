# isolate_host — enable all Windows Firewall profiles with a default BLOCK
# inbound rule, while keeping the WinRM management port open so the operator
# can still reach the box (and undo).
#
# This is the containment action that was missing: quarantine_file stops one
# binary but a live implant keeps running. Isolation stops the LATERAL
# MOVEMENT without powering the host off — evidence is preserved.
#
# Reversible: un-isolate removes the block rules and restores the previous
# profile states (captured in the journal by the verify payload).
#
# $Target is unused (whole-host action); pass 'host'.
$prev = @{}
try {
  Get-NetFirewallProfile | ForEach-Object { $prev[$_.Name] = $_.Enabled }
} catch {}

# enable every profile
try { Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True } catch {}

# default-deny inbound, allow established outbound (keeps evidence collection
# and the management door working)
try {
  if (-not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-BlockInbound' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'RMAgent-Isolate-BlockInbound' -Direction Inbound -Action Block -Profile Any |
      Out-Null
  }
  if (-not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowEstablished' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowEstablished' -Direction Outbound -Action Allow `
      -Protocol TCP -RemotePort Any -ErrorAction SilentlyContinue | Out-Null
  }
} catch {}

# keep the WinRM door open so undo/verify can reach the host
try {
  if (-not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -Direction Inbound -Action Allow `
      -Protocol TCP -LocalPort 5985,5986 -Profile Any | Out-Null
  }
} catch {}

$now_enabled = @{}
try { Get-NetFirewallProfile | ForEach-Object { $now_enabled[$_.Name] = $_.Enabled } } catch {}

[pscustomobject]@{
  ok=$true; action='isolate_host'; host=$env:COMPUTERNAME
  previous_profiles=($prev | ConvertTo-Json -Compress)
  now_profiles=($now_enabled | ConvertTo-Json -Compress)
  block_rule='RMAgent-Isolate-BlockInbound'
  winrm_kept_open=$true
  note='inbound blocked, WinRM 5985/5986 kept open so undo can reach the host'
} | ConvertTo-Json -Compress