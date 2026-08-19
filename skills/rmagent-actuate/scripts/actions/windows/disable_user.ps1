# disable_user — disable a local account (NEVER deletes). Engine injects $Target.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if (-not $u) {
  [pscustomobject]@{ action='disable_user'; user=$Target; status='not-found' } | ConvertTo-Json -Compress
} elseif (-not $u.Enabled) {
  [pscustomobject]@{ action='disable_user'; user=$Target; status='already-disabled' } | ConvertTo-Json -Compress
} else {
  Disable-LocalUser -Name $Target
  [pscustomobject]@{ action='disable_user'; user=$Target; status='disabled' } | ConvertTo-Json -Compress
}
