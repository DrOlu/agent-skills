# enable_netaudit - enable Filtering Platform Connection ({0CCE9225}) and
# Filtering Platform Packet Drop ({0CCE9226}) auditing (success+failure).
# Lights Security-log events 5156/5157 - per-connection telemetry with
# process and principal. The practical substitute where Sysmon EID3 cannot
# arm (platform bug). Reversible via disable_netaudit. No $Target.
$ErrorActionPreference='Stop'
$fpc='{0CCE9225-69AE-11D9-BED3-505054503030}'
$fppd='{0CCE9226-69AE-11D9-BED3-505054503030}'
try {
  auditpol /set /subcategory:$fpc /success:enable /failure:enable | Out-Null
  auditpol /set /subcategory:$fppd /success:enable /failure:enable | Out-Null
  $r1 = (auditpol /get /subcategory:$fpc /r | Out-String) -match 'Success'
  $r2 = (auditpol /get /subcategory:$fppd /r | Out-String) -match 'Success'
  $ok = ($r1 -and $r2)
  [pscustomobject]@{ action='enable_netaudit'; status= if($ok){'enabled'}else{'failed'}; filtering_platform_connection=$r1; packet_drop=$r2 } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ ok=$false; action='enable_netaudit'; error="$($_.Exception.Message)" } | ConvertTo-Json -Compress
}
