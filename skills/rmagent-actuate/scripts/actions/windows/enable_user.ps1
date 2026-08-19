# enable_user — re-enable a local account (undo of disable_user). Engine injects $Target.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if (-not $u) {
  [pscustomobject]@{ action='enable_user'; user=$Target; status='not-found' } | ConvertTo-Json -Compress
} elseif ($u.Enabled) {
  [pscustomobject]@{ action='enable_user'; user=$Target; status='already-enabled' } | ConvertTo-Json -Compress
} else {
  Enable-LocalUser -Name $Target
  [pscustomobject]@{ action='enable_user'; user=$Target; status='enabled' } | ConvertTo-Json -Compress
}
