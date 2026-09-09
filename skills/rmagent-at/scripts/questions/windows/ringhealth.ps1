# ringhealth — AutoLogger sessions Running? Circular? oldest event? Stopped = witness_blind.
# MOP created the sessions; this question is Phase 0 (read-only).
$now=[DateTime]::UtcNow
$names=@('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')
$rows=@()
$blind=0
foreach($n in $names){
  $st='missing'; $circ='unknown'; $bytes=0; $running=$false
  try{
    $q = logman query $n 2>$null | Out-String
    if($q -match 'Running'){ $st='Running'; $running=$true }
    elseif($q -match 'Stopped'){ $st='Stopped' }
    if($q -match 'Circular'){ $circ='On' }
    if($q -match 'File Name:\s+(\S+)'){ $fp=$Matches[1]; if(Test-Path $fp){ $bytes=(Get-Item $fp).Length } }
  }catch{ $st='error' }
  if(-not $running){ $blind++ }
  $rows += [pscustomobject]@{session=$n; status=$st; circular=$circ; bytes=$bytes}
}
[pscustomobject]@{
  skill='ringhealth'; host=$env:COMPUTERNAME; utc=$now.ToString('o')
  sessions=$rows; blind_count=$blind
  blind_check=$(if($blind -eq 0){'ok'}else{'BLIND'})
  note='Stopped AutoLogger is witness_blind for the app plane — not a quiet box'
}|ConvertTo-Json -Compress -Depth 4
