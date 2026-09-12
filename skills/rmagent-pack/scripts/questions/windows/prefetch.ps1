# prefetch — one-shot proof of execution. Capped. A hole if the artifact is absent.
# Engine injects: $Track $SinceHours $Limit (+ door/transport). Returns ONE JSON object.
# Recipe art.prefetch: fields Image/LastRun/count only. Never the .pf lake.
$hn=$env:COMPUTERNAME
$rows=@(); $n=0; $pf=0; $blind=$true
try{
  $dir="$env:SystemRoot\Prefetch"
  if(-not (Test-Path $dir)){ $blind=$true }
  else{
    $blind=$false
    $cut=(Get-Date).AddHours(-[double]$SinceHours)
    $files = Get-ChildItem "$dir\*.pf" -EA SilentlyContinue |
             Where-Object { $_.LastWriteTime -gt $cut } |
             Sort-Object LastWriteTime -Descending | Select-Object -First $Limit
    foreach($f in $files){
      $n++
      $img = ($f.Name -split '-')[0]
      # match the tracked principals' usual executables / anything *.exe by name
      $rows += [pscustomobject]@{
        Image = $img
        Path  = "$dir\$($f.Name)"
        LastRun = $f.LastWriteTimeUtc.ToString('o')
        Count = $null      # PF run-count needs parsing; left hole, not a lie
      }
    }
  }
}catch{}
# If prefetch is disabled (a common hardening/anti-forensic move) say so — a
# clean list here would be a false "nothing ran".
[pscustomobject]@{
  skill='prefetch';host=$hn;utc=[DateTime]::UtcNow.ToString('o')
  blind=$blind;n_rows=$n;parse_failures=$pf;rows=@($rows)
  note=$(if($blind){'prefetch absent or disabled — execution proof unavailable, not zero'}
         else{'capped pull; Count left null rather than fabricated'})
}|ConvertTo-Json -Compress -Depth 4
