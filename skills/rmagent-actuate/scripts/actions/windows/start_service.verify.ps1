# start_service.verify — confirm the service is running. Engine injects $Target.
$s = Get-Service -Name $Target -ErrorAction SilentlyContinue
if ($s -and $s.Status -eq 'Running') { 'VERIFIED' } else { 'NOT_VERIFIED' }
