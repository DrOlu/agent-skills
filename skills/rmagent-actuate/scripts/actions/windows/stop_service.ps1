# stop_service - stop + disable a service (never deletes it). Engine injects $Target.
# REV 17 (C4): Stop + observe - the observed state (Status + StartType) is
# returned, not the intended one.
$ErrorActionPreference = 'Stop'
try {
  $svc = Get-Service -Name $Target -ErrorAction SilentlyContinue
  if (-not $svc) {
    [pscustomobject]@{ action='stop_service'; service=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    Stop-Service -Name $Target -Force -ErrorAction Stop
    Set-Service -Name $Target -StartupType Disabled -ErrorAction Stop
    # observe: what is the service REALLY doing now?
    $s = Get-Service -Name $Target
    $ok_state = ($s.Status -eq 'Stopped')
    [pscustomobject]@{ action='stop_service'; service=$Target;
                       status= if($ok_state){'stopped'}else{'failed'};
                       state=$s.Status; startup=(Get-CimInstance Win32_Service -Filter "Name='$Target'").StartMode } | ConvertTo-Json -Compress
  }
} catch {
  $s = $null
  try { $s = Get-Service -Name $Target -ErrorAction SilentlyContinue } catch {}
  [pscustomobject]@{ok=$false; action='stop_service'; service=$Target;
                     error="$($_.Exception.Message)";
                     observed_state= if($s){[string]$s.Status}else{'unknown'} } | ConvertTo-Json -Compress
}
