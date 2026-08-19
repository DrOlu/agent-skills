# add_admin.verify — confirm the account is back in Administrators. Engine injects $Target.
$now = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" }).Count
if ($now -gt 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
