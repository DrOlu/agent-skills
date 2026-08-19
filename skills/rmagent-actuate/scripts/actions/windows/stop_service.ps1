# stop_service — stop + disable a service (never deletes it). Engine injects $Target.
$svc = Get-Service -Name $Target -ErrorAction SilentlyContinue
if (-not $svc) {
  [pscustomobject]@{ action='stop_service'; service=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  Stop-Service -Name $Target -Force -ErrorAction SilentlyContinue
  Set-Service -Name $Target -StartupType Disabled -ErrorAction SilentlyContinue
  $s = Get-Service -Name $Target
  [pscustomobject]@{ action='stop_service'; service=$Target; status='stopped'; state=$s.Status } | ConvertTo-Json -Compress
}
