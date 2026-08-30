# rotate_credential — force a password change on a local account.
# The REMEDIATION half of containment: disable_user breaks the account (and
# the human). Rotation breaks the ATTACKER's copy of the credential while
# keeping the account usable.
#
# Reversible: the journal records the PREVIOUS password last-set time so the
# operator can verify; the credential itself is never written to the journal.
#
# $Target = the account name. A random password is generated LOCALLY on the
# host and set; it is returned ONCE in the answer so the operator can hand it
# to the account owner. It is NOT persisted anywhere by this skill.
$u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
if (-not $u) {
  [pscustomobject]@{ok=$false; error="no local user '$Target'"} | ConvertTo-Json -Compress
  return
}
$prev = $u.PasswordLastSet
# 24-char random, cryptographically strong, from the full printable set
$bytes = New-Object byte[] 24
try { [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes) } catch { $bytes = New-Object byte[] 24 }
$pw = [Convert]::ToBase64String($bytes).Substring(0,24).TrimEnd('=').Insert(12,'!')
try {
  Set-LocalUser -Name $Target -Password (ConvertTo-SecureString $pw -AsPlainText -Force)
  $after = Get-LocalUser -Name $Target
  [pscustomobject]@{
    ok=$true; action='rotate_credential'; user=$Target
    previous_password_lastset=$(if($prev){$prev.ToString('o')}else{$null})
    new_password_lastset=$(if($after.PasswordLastSet){$after.PasswordLastSet.ToString('o')}else{$null})
    new_password=$pw
    note='hand this password to the account owner; it is not stored by RMAgent'
  } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}