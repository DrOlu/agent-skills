# restore_file - remove the deny-execute ACE (undo of quarantine_file). Engine injects $Target.
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  if (-not (Test-Path $Target)) {
    [pscustomobject]@{ action='restore_file'; path=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    $acl = Get-Acl $Target
    $denies = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' })
    foreach ($d in $denies) { $acl.RemoveAccessRule($d) | Out-Null }
    Set-Acl $Target $acl
    $after = Get-Acl $Target
    $left = @($after.Access | Where-Object { $_.AccessControlType -eq 'Deny' -and $_.FileSystemRights -match 'Execute' }).Count
    [pscustomobject]@{ action='restore_file'; path=$Target;
                       status= if($left -eq 0){'restored'}else{'failed'}; removed_aces=$denies.Count; deny_aces_left=$left } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='restore_file'; path=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
