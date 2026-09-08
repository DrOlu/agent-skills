# switch_txn — rows for $Ticket from Postilion-like journal. Filter on device. Mask PAN. Never PIN.
$t = ($Ticket + '') -replace '^(RRN|STAN)-',''
$rows = @()
try {
  if (-not $Artifact) { @{skill='switch_txn';ok=$false;error='no artifact path';rows=@()} | ConvertTo-Json -Compress; return }
  $files = @(Get-Item $Artifact -EA SilentlyContinue) | Select-Object -First 8
  foreach ($f in $files) {
    Get-Content $f.FullName -EA SilentlyContinue | Select-Object -First 4000 | ForEach-Object {
      if ($t -and ($_ -notmatch [regex]::Escape($t))) { return }
      $stan=$null;$rrn=$null;$term=$null;$rc=$null;$pan=$null;$mts=$null
      if ($_ -match '(?i)stan[=: ]+(\w+)') { $stan=$Matches[1] }
      if ($_ -match '(?i)rrn[=: ]+(\w+)') { $rrn=$Matches[1] }
      if ($_ -match '(?i)term(?:inal)?[=: ]+(\w+)') { $term=$Matches[1] }
      if ($_ -match '(?i)rc[=: ]+(\w+)') { $rc=$Matches[1] }
      if ($_ -match '(?:^|,)(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)') { $mts=$Matches[1] }
      if ($_ -match '\b(5\d{15,18})\b') {
        $d=$Matches[1]; if ($d.Length -ge 10) { $pan = $d.Substring(0,6) + ('*'*($d.Length-10)) + $d.Substring($d.Length-4) }
      }
      if ($stan -or $rrn) {
        $rows += [pscustomobject]@{stan=$stan;rrn=$rrn;terminal_id=$term;in_ts=$mts;out_ts=$null;rc=$rc;pan=$pan}
      }
    }
    if ($rows.Count -ge $Limit) { break }
  }
} catch {}
if ($rows.Count -gt $Limit) { $rows = $rows | Select-Object -First $Limit }
@{skill='switch_txn';host=$env:COMPUTERNAME;rows=@($rows)} | ConvertTo-Json -Compress -Depth 4
