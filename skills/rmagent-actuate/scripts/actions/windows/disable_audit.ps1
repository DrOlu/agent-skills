# disable_audit - undo of enable_audit: disable Directory Service Changes
# auditing (success+failure). Fixed subcategory GUID, no $Target.
$ErrorActionPreference='Stop'
$guid='{0CCE923F-69AE-11D9-BED3-505054503030}'
try {
  auditpol /set /subcategory:$guid /success:disable /failure:disable | Out-Null
  $rep = (auditpol /get /subcategory:$guid /r) | Out-String
  $ok_state = -not ($rep -match 'Success')
  [pscustomobject]@{ action='disable_audit'; subcategory='Directory Service Changes ({0CCE923F-69AE-11D9-BED3-505054503030})'; status= if($ok_state){'disabled'}else{'failed'} } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ ok=$false; action='disable_audit'; error="$($_.Exception.Message)" } | ConvertTo-Json -Compress
}
