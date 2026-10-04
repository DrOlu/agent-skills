# disable_netaudit - undo of enable_netaudit: disable Filtering Platform
# Connection ({0CCE9225}) and Packet Drop ({0CCE9226}) auditing.
$ErrorActionPreference='Stop'
$fpc='{0CCE9225-69AE-11D9-BED3-505054503030}'
$fppd='{0CCE9226-69AE-11D9-BED3-505054503030}'
try {
  auditpol /set /subcategory:$fpc /success:disable /failure:disable | Out-Null
  auditpol /set /subcategory:$fppd /success:disable /failure:disable | Out-Null
  $r1 = -not ((auditpol /get /subcategory:$fpc /r | Out-String) -match 'Success')
  $r2 = -not ((auditpol /get /subcategory:$fppd /r | Out-String) -match 'Success')
  $ok = ($r1 -and $r2)
  [pscustomobject]@{ action='disable_netaudit'; status= if($ok){'disabled'}else{'failed'} } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ ok=$false; action='disable_netaudit'; error="$($_.Exception.Message)" } | ConvertTo-Json -Compress
}
