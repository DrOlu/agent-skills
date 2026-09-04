# verify: plant_canary — the decoy must EXIST and be DISABLED.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if ($u -and -not $u.Enabled) { 'VERIFIED' } else { 'NOT_VERIFIED' }