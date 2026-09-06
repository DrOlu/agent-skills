# enable_user - re-enable a local account (undo of disable_user). Engine injects $Target.
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $u = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
  if (-not $u) {
    [pscustomobject]@{ action='enable_user'; user=$Target; status='not-found' } | ConvertTo-Json -Compress
  } elseif ($u.Enabled) {
    [pscustomobject]@{ action='enable_user'; user=$Target; status='already-enabled' } | ConvertTo-Json -Compress
  } else {
    Enable-LocalUser -Name $Target
    $after = Get-LocalUser -Name $Target -ErrorAction SilentlyContinue
    [pscustomobject]@{ action='enable_user'; user=$Target;
                       status= if($after -and $after.Enabled){'enabled'}else{'failed'} } | ConvertTo-Json -Compress
  }
} catch {
  [pscustomobject]@{ok=$false; action='enable_user'; user=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
