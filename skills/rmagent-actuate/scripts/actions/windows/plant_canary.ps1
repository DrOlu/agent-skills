# plant_canary — create the decoy identity that makes patient-zero a tripwire.
#
# The decoy is DISABLED by default: it can never log on successfully, so it
# cannot be used as a foothold. But Windows still records every ATTEMPT
# against it (4625), which is exactly what the canary question reads.
# REV 17 (C4): Stop + observe.
#
# $Target = the decoy account name.
$ErrorActionPreference = 'Stop'
try {
  $u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
  if ($u) {
    if ($u.Enabled) { Disable-LocalUser -Name $Target }
    Set-LocalUser -Name $Target -PasswordNeverExpires $true -Description 'RMAgent canary - decoy, do not use' -ErrorAction SilentlyContinue
    $after = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
    [pscustomobject]@{ok=$true; action='plant_canary'; user=$Target; existed=$true;
                       enabled= if($after){-not $after.Enabled}else{$true};
                       status= if($after -and -not $after.Enabled){'planted'}else{'failed'};
                       note='decoy already present; kept disabled'} | ConvertTo-Json -Compress
    return
  }
  # Complexity-safe: upper, lower, digit and symbol in a long random string.
  $b = New-Object byte[] 32
  try { [System.Security.Cryptography.RandomNumberGenerator]::Fill($b) } catch { $b = New-Object byte[] 32 }
  $pw = [Convert]::ToBase64String($b).Substring(0,24).TrimEnd('=') + '!Aa9'
  New-LocalUser -Name $Target -Password (ConvertTo-SecureString $pw -AsPlainText -Force) `
    -Description 'RMAgent canary - decoy, do not use' -AccountNeverExpires -ErrorAction Stop | Out-Null
  Disable-LocalUser -Name $Target
  $after = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
  [pscustomobject]@{ok=$true; action='plant_canary'; user=$Target; existed=$false;
                     enabled= if($after){-not $after.Enabled}else{$true};
                     status= if($after -and -not $after.Enabled){'planted'}else{'failed'};
                     note='decoy planted, disabled, complexity-safe random password, never expires'} | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; action='plant_canary'; user=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
