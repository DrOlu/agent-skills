# enable_audit - enable Directory Service Changes auditing (success+failure)
# on a domain controller. Fixed subcategory GUID {0CCE923F-69AE-11D9-BED3-
# 505054503030} - no $Target. Reversible via disable_audit. Lights the
# attest blind_check 'DC-Audit' source.
$ErrorActionPreference='Stop'
$guid='{0CCE923F-69AE-11D9-BED3-505054503030}'
try {
  auditpol /set /subcategory:$guid /success:enable /failure:enable | Out-Null
  $rep = (auditpol /get /subcategory:$guid /r) | Out-String
  $ok_state = ($rep -match 'Success')
  $row = (($rep -split "`r?`n") | Where-Object {$_ -match $guid} | Select-Object -First 1)
  [pscustomobject]@{ action='enable_audit'; subcategory='Directory Service Changes ({0CCE923F-69AE-11D9-BED3-505054503030})'; status= if($ok_state){'enabled'}else{'failed'}; auditpol_row=$row } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ ok=$false; action='enable_audit'; error="$($_.Exception.Message)" } | ConvertTo-Json -Compress
}
