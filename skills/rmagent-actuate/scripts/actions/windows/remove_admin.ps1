# remove_admin - remove an account from the local Administrators group. Engine injects $Target.
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $NET = "$env:SystemRoot\System32\net.exe"
  $members = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" })
  if ($members.Count -eq 0) {
    [pscustomobject]@{ action='remove_admin'; user=$Target; status='not-in-group' } | ConvertTo-Json -Compress
  } else {
    & $NET localgroup Administrators $Target /delete 2>$null | Out-Null
    $still = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" }).Count
    [pscustomobject]@{ action='remove_admin'; user=$Target; status= if($still -eq 0){'removed'}else{'failed'} } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='remove_admin'; user=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
