# pay_sketch — counts only, no row dump
$t = ($Ticket + '') -replace '^(RRN|STAN)-',''
$n=0; $to=0; $by=@{}
try {
  foreach ($f in @(Get-Item $Artifact -EA SilentlyContinue) | Select-Object -First 5) {
    Get-Content $f.FullName -EA SilentlyContinue | Select-Object -First 2000 | ForEach-Object {
      if ($t -and ($_ -notmatch [regex]::Escape($t))) { return }
      $n++
      $rc='?'
      if ($_ -match '(?i)rc[=: ]+(\w+)') { $rc=$Matches[1] }
      if (-not $by.ContainsKey($rc)) { $by[$rc]=0 }
      $by[$rc]++
      if ($rc -in @('91','68')) { $to++ }
    }
  }
} catch {}
@{skill='pay_sketch';host=$env:COMPUTERNAME;n=$n;timeouts=$to;by_rc=$by} | ConvertTo-Json -Compress
