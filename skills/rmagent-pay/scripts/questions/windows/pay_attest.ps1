# pay_attest — can this hop's artifact see STAN/RRN? Engine injects $Artifact $Ticket $Limit $SinceHours
$out = [ordered]@{skill='pay_attest';host=$env:COMPUTERNAME;artifact=$Artifact;exists=$false;has_stan=$false;has_rrn=$false;n_rows=0;oldest=$null;blind=$true}
try {
  $files = @()
  if ($Artifact) { $files = @(Get-Item $Artifact -EA SilentlyContinue) }
  if (-not $files.Count) { $out | ConvertTo-Json -Compress; return }
  $out.exists = $true
  $n=0; $oldest=$null
  foreach ($f in $files | Select-Object -First 5) {
    $lines = Get-Content -Path $f.FullName -TotalCount 80 -EA SilentlyContinue
    foreach ($l in $lines) {
      $n++
      if ($l -match '(?i)stan|f11') { $out.has_stan = $true }
      if ($l -match '(?i)rrn|f37|retrieval') { $out.has_rrn = $true }
      if (-not $oldest) { $oldest = $f.LastWriteTimeUtc.ToString('o') }
    }
  }
  $out.n_rows = $n
  $out.oldest = $oldest
  $out.blind = -not ($out.has_stan -or $out.has_rrn)
} catch {}
$out | ConvertTo-Json -Compress
