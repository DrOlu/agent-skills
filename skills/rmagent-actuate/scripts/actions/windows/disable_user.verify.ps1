# disable_user.verify — confirm the account exists and is disabled. Engine injects $Target.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if ($u -and -not $u.Enabled) { 'VERIFIED' } else { 'NOT_VERIFIED' }
