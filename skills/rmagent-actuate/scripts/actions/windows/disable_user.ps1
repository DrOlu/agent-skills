# disable_user - disable a local account (NEVER deletes). Engine injects $Target.
# REV 17 (C4): Stop + observe - a failed Disable-LocalUser can never again
# report status='disabled'.
$ErrorActionPreference = 'Stop'
try {
  $u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
  if (-not $u) {
    [pscustomobject]@{ action='disable_user'; user=$Target; status='not-found' } | ConvertTo-Json -Compress
  } elseif (-not $u.Enabled) {
    [pscustomobject]@{ action='disable_user'; user=$Target; status='already-disabled' } | ConvertTo-Json -Compress
  } else {
    Disable-LocalUser -Name $Target
    # observe: is the account REALLY disabled?
    $after = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
    [pscustomobject]@{ action='disable_user'; user=$Target;
                       status= if($after -and -not $after.Enabled){'disabled'}else{'failed'} } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='disable_user'; user=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
