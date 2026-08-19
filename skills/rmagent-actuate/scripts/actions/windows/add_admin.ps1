# add_admin — add an account back to Administrators (undo of remove_admin). Engine injects $Target.
$NET = "$env:SystemRoot\System32\net.exe"
$inGroup = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" }).Count
if ($inGroup -gt 0) {
  [pscustomobject]@{ action='add_admin'; user=$Target; status='already-in-group' } | ConvertTo-Json -Compress
} else {
  & $NET localgroup Administrators $Target /add 2>$null | Out-Null
  $now = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" }).Count
  [pscustomobject]@{ action='add_admin'; user=$Target; status= if($now -gt 0){'added'}else{'failed'} } | ConvertTo-Json -Compress
}
