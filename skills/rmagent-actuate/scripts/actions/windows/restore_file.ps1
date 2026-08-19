# restore_file — remove the deny-execute ACE (undo of quarantine_file). Engine injects $Target.
if (-not (Test-Path $Target)) {
  [pscustomobject]@{ action='restore_file'; path=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  $acl = Get-Acl $Target
  $denies = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' })
  foreach ($d in $denies) { $acl.RemoveAccessRule($d) | Out-Null }
  Set-Acl $Target $acl
  [pscustomobject]@{ action='restore_file'; path=$Target; status='restored'; removed_aces=$denies.Count } | ConvertTo-Json -Compress
}
