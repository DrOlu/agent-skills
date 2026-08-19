# quarantine_file.verify — confirm a deny-execute ACE is present. Engine injects $Target.
if (Test-Path $Target) {
  $acl = Get-Acl $Target
  $deny = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' }).Count
  if ($deny -gt 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
} else { 'NOT_VERIFIED' }
