# remove_admin.verify — confirm the account is out of Administrators. Engine injects $Target.
$still = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "\\$Target`$" }).Count
if ($still -eq 0) { 'VERIFIED' } else { 'NOT_VERIFIED' }
