# restart_sysmon - re-arm the Sysmon driver network hook (EID3).
# Restart-Service first; if the stop is blocked (driver pinned - the normal
# state), fall back to the vendor-supported sysmon64 -u + -i with the SAME
# config file (C:\ProgramData\rmagent\rmagent_sysmon_v6.xml). Brief logging
# pause; no traffic impact.
$ErrorActionPreference='Stop'
$bin='C:\Windows\Sysmon64.exe'
$cfg='C:\ProgramData\rmagent\rmagent_sysmon_v6.xml'
try {
  $before=(Get-Service Sysmon64).StartType
  $method='restart-service'
  try {
    Restart-Service Sysmon64 -Force -ErrorAction Stop
  } catch {
    $method='reinstall (-u then -i same config)'
    $null = (& $bin -u 2>&1)
    Start-Sleep -Seconds 4
    $null = (& $bin -accepteula -i $cfg 2>&1)
    Start-Sleep -Seconds 4
  }
  $svc=Get-Service Sysmon64
  $ok = ($svc.Status -eq 'Running')
  [pscustomobject]@{action='restart_sysmon'; method=$method; status= if($ok){'restarted'}else{'failed'}; state=$svc.Status; startup=$svc.StartType; previous_startup=$before} | ConvertTo-Json -Compress
} catch {
  $s=$null; try{$s=(Get-Service Sysmon64).Status}catch{}
  [pscustomobject]@{ok=$false; action='restart_sysmon'; error="$($_.Exception.Message)"; observed_state= if($s){[string]$s}else{'unknown'}} | ConvertTo-Json -Compress
}
