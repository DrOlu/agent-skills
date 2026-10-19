# livewindow — bounded live ETW tap (Model 1). Built-in tools only: logman +
# Get-WinEvent. ONE deliberate carve-out from read-only, disclosed in-band:
# a single .etl trace file under $env:TEMP for the window, then removed.
$P='A0C1853B-5C40-4B15-8766-34CF5B55B7D5'
$s='rwLW'+([guid]::NewGuid().ToString('N').Substring(0,6))
$carve=[ordered]@{temp_file='';bytes_written=0;removed=$false;session_stopped=$false;stale_stopped=0}
try{foreach($q in (logman query -ets 2>$null|Select-String 'rwLW')){$n=@($q.ToString() -split '\s+'|Where-Object{$_ -like 'rwLW*'})[0];if($n){logman stop $n -ets 2>$null|Out-Null;$carve.stale_stopped++}}}catch{}
$etl=Join-Path $env:TEMP ($s+'.etl')
$carve.temp_file=$etl
logman create trace $s -p ('{'+$P+'}') 0xffffffff -o $etl -ets 2>$null|Out-Null
Start-Sleep -Seconds 15
logman stop $s -ets 2>$null|Out-Null
if($LASTEXITCODE -eq 0){$carve.session_stopped=$true}
$ev=@();try{$ev=@(Get-WinEvent -Path $etl -Oldest -ErrorAction Stop)}catch{}
$BAD=@('iex','invoke-expression','downloadstring','downloadfile','frombase64','-enc','bypass','http://','https://','net.webclient','add-type','schtasks','regsvr32')
$rows=@();foreach($x in $ev){if($rows.Count -ge $Limit){break}
 $m=[string]$x.Message;if($m.Length -gt $MsgCap){$m=$m.Substring(0,$MsgCap)}
 $low=$m.ToLower();$fl=@($BAD|Where-Object{$low -match [regex]::Escape($_)}).Count -gt 0
 $rows+=[pscustomobject]@{t=$x.TimeCreated.ToUniversalTime().ToString('o');id=$x.Id;lvl=$x.LevelDisplayName;flag=$fl;msg=$m}}
$carve.bytes_written=(Get-Item $etl -ErrorAction SilentlyContinue).Length
Remove-Item $etl -Force -ErrorAction SilentlyContinue
$carve.removed=-not (Test-Path $etl)
[pscustomobject]@{skill='livewindow';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');provider=$P;window_seconds=15;events_seen=$ev.Count;events=$rows;carve_out=$carve;carve_note='WRITE CARVE-OUT: one .etl trace file in $env:TEMP during a 15s window, then deleted; trace session stopped in-band; stale rwLW sessions reaped; nothing else written'}|ConvertTo-Json -Compress -Depth 4
