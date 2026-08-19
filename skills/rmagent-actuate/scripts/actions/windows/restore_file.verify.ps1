# restore_file.verify — confirm no deny-execute ACE remains. Engine injects $Target.
if (Test-Path $Target) {
  $acl = Get-Acl $Target
  $deny = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' }).Count
  if ($deny -eq 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
} else { 'VERIFIED' }
