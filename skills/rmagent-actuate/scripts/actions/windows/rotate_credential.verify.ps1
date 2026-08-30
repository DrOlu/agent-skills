# verify: rotate_credential — the password last-set time must have MOVED.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if ($u -and $u.PasswordLastSet -and ((Get-Date) - $u.PasswordLastSet).TotalMinutes -lt 10) {
  'VERIFIED'
} else {
  'NOT-VERIFIED'
}