# amcache — execution provenance (first-seen). Capped. Hole if the hive is absent.
# Recipe art.amcache: Path / FirstSeen / sha1 only.
$hn=$env:COMPUTERNAME
$rows=@(); $n=0; $blind=$true
$hive="$env:SystemRoot\AppCompat\Programs\Amcache.hve"
try{
  if(Test-Path $hive){
    $blind=$false
    # Reading a hive live is unsafe; use the reg export path for the one key.
    $tmp="$env:TEMP\rmagent-amcache.txt"
    & "$env:SystemRoot\System32\reg.exe" export "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppCompatUpgradeInventory\Root" $tmp /y 2>&1 | Out-Null
    if(Test-Path $tmp){
      $cut=(Get-Date).AddHours(-[double]$SinceHours)
      $rows = Get-Content $tmp -EA SilentlyContinue |
        Select-String -Pattern '\\+[A-Za-z0-9_\-\.]+\.exe$' |
        Select-Object -First $Limit |
        ForEach-Object { $n++; [pscustomobject]@{ Path=$_.Line.Trim(); FirstSeen=$null } }
      Remove-Item $tmp -Force -EA SilentlyContinue
    }
  }
}catch{}
[pscustomobject]@{skill='amcache';host=$hn;utc=[DateTime]::UtcNow.ToString('o')
  blind=$blind;n_rows=$n;rows=@($rows)
  note=$(if($blind){'Amcache hive absent — first-seen provenance unavailable'}
         else{'live-hive read is unsafe; export-based, capped'})
}|ConvertTo-Json -Compress -Depth 4
