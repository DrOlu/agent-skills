# enable_user.verify — confirm the account is enabled. Engine injects $Target.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if ($u -and $u.Enabled) { 'VERIFIED' } else { 'NOT_VERIFIED' }
