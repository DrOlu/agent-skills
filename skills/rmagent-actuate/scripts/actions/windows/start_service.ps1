# start_service - re-enable + start a service (undo of stop_service). Engine injects $Target.
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $svc = Get-Service -Name $Target -ErrorAction SilentlyContinue
  if (-not $svc) {
    [pscustomobject]@{ action='start_service'; service=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    Set-Service -Name $Target -StartupType Automatic -ErrorAction Stop
    Start-Service -Name $Target -ErrorAction Stop
    $s = Get-Service -Name $Target
    [pscustomobject]@{ action='start_service'; service=$Target;
                       status= if($s.Status -eq 'Running'){'started'}else{'failed'}; state=$s.Status } | ConvertTo-Json -Compress
  }
} catch {
  $s = $null
  try { $s = Get-Service -Name $Target -ErrorAction SilentlyContinue } catch {}
  [pscustomobject]@{ok=$false; action='start_service'; service=$Target;
                     error="$($_.Exception.Message)";
                     observed_state= if($s){[string]$s.Status}else{'unknown'} } | ConvertTo-Json -Compress
}
