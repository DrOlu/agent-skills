# quarantine_file — deny execute on a file via ACL (file stays for forensics).
# Engine injects $Target (file path).
if (-not (Test-Path $Target)) {
  [pscustomobject]@{ action='quarantine_file'; path=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  $acl = Get-Acl $Target
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule('Everyone','ExecuteFile','Deny')
  $acl.AddAccessRule($rule)
  Set-Acl $Target $acl
  [pscustomobject]@{ action='quarantine_file'; path=$Target; status='quarantined' } | ConvertTo-Json -Compress
}
