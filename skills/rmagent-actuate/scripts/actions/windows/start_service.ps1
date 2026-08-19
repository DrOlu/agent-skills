# start_service — re-enable + start a service (undo of stop_service). Engine injects $Target.
$svc = Get-Service -Name $Target -ErrorAction SilentlyContinue
if (-not $svc) {
  [pscustomobject]@{ action='start_service'; service=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  Set-Service -Name $Target -StartupType Automatic -ErrorAction SilentlyContinue
  Start-Service -Name $Target -ErrorAction SilentlyContinue
  $s = Get-Service -Name $Target
  [pscustomobject]@{ action='start_service'; service=$Target; status='started'; state=$s.Status } | ConvertTo-Json -Compress
}
