# isolate_host — block ALL inbound via the profile DEFAULT, not a Block rule.
#
# REV 17 (C2) — the old design was a lockout: it created an explicit
# BlockInbound rule and a separate Allow rule for WinRM 5985/5986. Windows
# Firewall evaluates explicit BLOCK rules BEFORE explicit Allow rules, so
# the WinRM allow was overridden — the operator (and the undo) could never
# reach the box again. It had only ever been dry-run, so nobody was locked
# out, but the action whose undo MUST work was the one that couldn't.
#
# The new design does not fight rule precedence. The profile DEFAULT inbound
# action is evaluated AFTER all allow rules, so:
#   1. journal the current DefaultInboundAction per profile + the names of
#      enabled inbound Allow rules (names only — small, no lake)
#   2. create RMAgent-Isolate-AllowWinRM FIRST (an allow rule beats the
#      profile default)
#   3. set every profile's DefaultInboundAction to Block
#   4. disable every OTHER enabled inbound Allow rule (so the default
#      actually applies) — names captured in step 1 let the undo re-enable
#      exactly what was there before
#
# Outbound is left alone (allow-by-default; blocking it would kill evidence
# collection and C2 beaconing we WANT to observe).
#
# $Target is unused (whole-host action); pass 'host'.
$ErrorActionPreference = 'Stop'
try {
  # --- 1. capture the pre-state (goes to the journal via result_detail) ---
  $prevDefault = @{}
  foreach ($p in (Get-NetFirewallProfile -ErrorAction Stop)) {
    $prevDefault[$p.Name] = [string]$p.DefaultInboundAction
  }
  $prevAllowRules = @()
  $prevAllowRules = @(Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' } |
    ForEach-Object { $_.DisplayName })

  # --- 2. WinRM allow FIRST — an allow rule outranks the profile default ---
  if (-not (Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -Direction Inbound -Action Allow `
      -Protocol TCP -LocalPort 5985,5986 -Profile Any | Out-Null
  }

  # --- 3. every profile ON with a Block default inbound ---
  Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
  Set-NetFirewallProfile -Profile Domain,Public,Private -DefaultInboundAction Block

  # --- 4. disable every other inbound allow so the default takes effect ---
  $disabled = @()
  foreach ($r in (Get-NetFirewallRule -Direction Inbound -Action Allow -ErrorAction SilentlyContinue)) {
    if ($r.Enabled -eq 'True' -and $r.DisplayName -ne 'RMAgent-Isolate-AllowWinRM') {
      Disable-NetFirewallRule -DisplayName $r.DisplayName -ErrorAction SilentlyContinue
      $disabled += $r.DisplayName
    }
  }

  # --- verify what we actually observe, not what we intended ---
  $nowDefault = @{}
  foreach ($p in (Get-NetFirewallProfile)) { $nowDefault[$p.Name] = [string]$p.DefaultInboundAction }
  $winrmOpen = [bool](Get-NetFirewallRule -DisplayName 'RMAgent-Isolate-AllowWinRM' -ErrorAction SilentlyContinue)
  $isolated = ($nowDefault.Values | Where-Object { $_ -ne 'Block' }).Count -eq 0 -and $winrmOpen

  [pscustomobject]@{
    ok=$true; action='isolate_host'; host=$env:COMPUTERNAME
    previous_default_inbound=($prevDefault | ConvertTo-Json -Compress)
    previous_allow_rules=($prevAllowRules | Select-Object -First 200)
    disabled_allow_rules=($disabled | Select-Object -First 200)
    now_default_inbound=($nowDefault | ConvertTo-Json -Compress)
    winrm_rule_present=$winrmOpen
    status= if($isolated){'isolated'}else{'partial'}
    note='inbound blocked via profile default; WinRM 5985/5986 allowed by rule (beats the default); undo re-enables the journaled rules'
  } | ConvertTo-Json -Compress -Depth 4
} catch {
  [pscustomobject]@{ok=$false; action='isolate_host'; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
