# core_auth — Finacle-like auth log on Windows (rare). Same contract as linux core_auth.sh
$t = ($Ticket + '') -replace '^(RRN|STAN)-',''
$rows = @()
try {
  if (-not $Artifact) { @{skill='core_auth';error='no artifact';rows=@()} | ConvertTo-Json -Compress; return }
  foreach ($f in @(Get-Item $Artifact -EA SilentlyContinue) | Select-Object -First 8) {
    Get-Content $f.FullName -EA SilentlyContinue | Select-Object -First 4000 | ForEach-Object {
      if ($t -and ($_ -notmatch [regex]::Escape($t))) { return }
      $stan=$null;$rrn=$null;$rc=$null;$recv=$null;$post=$null
      if ($_ -match '(?i)stan[=: ]+(\w+)') { $stan=$Matches[1] }
      if ($_ -match '(?i)rrn[=: ]+(\w+)') { $rrn=$Matches[1] }
      if ($_ -match '(?i)rc[=: ]+(\w+)') { $rc=$Matches[1] }
      if ($_ -match '(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)') { $recv=$Matches[1] }
      if ($stan -or $rrn) { $rows += [pscustomobject]@{stan=$stan;rrn=$rrn;recv_ts=$recv;post_ts=$post;rc=$rc} }
    }
    if ($rows.Count -ge $Limit) { break }
  }
} catch {}
@{skill='core_auth';host=$env:COMPUTERNAME;rows=@($rows | Select-Object -First $Limit)} | ConvertTo-Json -Compress -Depth 4
