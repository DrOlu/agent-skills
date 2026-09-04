# rotate_credential — force a password change on a local account.
# The REMEDIATION half of containment: disable_user breaks the account (and
# the human). Rotation breaks the ATTACKER's copy of the credential while
# keeping the account usable.
#
# REV 17 (C5): the new password is returned ONCE for the operator to hand to
# the account owner. The ENGINE strips it from result_detail before the
# journal sees it (REDACT_KEYS); the journal records only the previous/new
# PasswordLastSet times so the change is verifiable without the secret.
#
# $Target = the account name. A random password is generated LOCALLY on the
# host and set.
$ErrorActionPreference = 'Stop'
try {
  $u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
  if (-not $u) {
    [pscustomobject]@{ok=$false; error="no local user '$Target'"} | ConvertTo-Json -Compress
    return
  }
  $prev = $u.PasswordLastSet
  # 24-char random, cryptographically strong, from the full printable set
  $bytes = New-Object byte[] 24
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $pw = [Convert]::ToBase64String($bytes).Substring(0,24).TrimEnd('=').Insert(12,'!')
  Set-LocalUser -Name $Target -Password (ConvertTo-SecureString $pw -AsPlainText -Force)
  $after = Get-LocalUser -Name $Target
  [pscustomobject]@{
    ok=$true; action='rotate_credential'; user=$Target
    previous_password_lastset=$(if($prev){$prev.ToString('o')}else{$null})
    new_password_lastset=$(if($after.PasswordLastSet){$after.PasswordLastSet.ToString('o')}else{$null})
    new_password=$pw
    note='hand this password to the account owner; the journal records only the last-set times'
  } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; action='rotate_credential'; user=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
