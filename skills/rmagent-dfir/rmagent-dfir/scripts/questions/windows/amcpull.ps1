# amcpull — Amcache.hve probe: existence, size, mtime, SHA256, readability.
# The hive is never parsed on-box; acquire via dfir.py collect (ircollect) and
# parse offline with amcache_parse.py.
$P='C:\Windows\appcompat\Programs\Amcache.hve'
$r=[ordered]@{exists=$false};try{if(Test-Path $P){$i=Get-Item $P;$r.exists=$true;$r.size=$i.Length;$r.mtime=($i.LastWriteTimeUtc.ToString('o'));$r.sha256=(Get-FileHash $P -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower();$fs=[IO.File]::Open($P,'Open','Read','ReadWrite');$null=$fs.ReadByte();$fs.Close();$r.readable=$true}else{$r.note='not present - Amcache disabled or legacy host'}}catch{$r.readable=$false;$m=$_.Exception.Message;if($m.Length -gt 110){$m=$m.Substring(0,110)+'…'};$r.note='locked or unreadable: '+$m}
[pscustomobject]@{skill='amcpull';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');amcache=$r;offline_parse='amcache_parse.py on the ircollect copy'}|ConvertTo-Json -Compress -Depth 4
