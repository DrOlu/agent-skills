# quarantine_file - deny execute on a file via ACL (file stays for forensics).
# Engine injects $Target (file path).
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  if (-not (Test-Path $Target)) {
    [pscustomobject]@{ action='quarantine_file'; path=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    $acl = Get-Acl $Target
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule('Everyone','ExecuteFile','Deny')
    $acl.AddAccessRule($rule)
    Set-Acl $Target $acl
    $after = Get-Acl $Target
    $deny = @($after.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' }).Count
    [pscustomobject]@{ action='quarantine_file'; path=$Target;
                       status= if($deny -gt 0){'quarantined'}else{'failed'}; deny_aces=$deny } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='quarantine_file'; path=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
