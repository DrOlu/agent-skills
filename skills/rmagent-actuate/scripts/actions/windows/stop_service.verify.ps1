# stop_service.verify — confirm the service is stopped and disabled. Engine injects $Target.
$s = Get-Service -Name $Target -ErrorAction SilentlyContinue
if ($s -and $s.Status -eq 'Stopped') { 'VERIFIED' } else { 'NOT_VERIFIED' }
