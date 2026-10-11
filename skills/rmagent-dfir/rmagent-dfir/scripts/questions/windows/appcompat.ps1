# appcompat — Shimcache (AppCompatCache) blob from the live SYSTEM hive.
# The blob is base64; parsing happens on the jump host (dfir.py), never on
# the witness. Capped: the parser sees what the cap kept, holes are honest.
$v='';try{$v=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\AppCompatCache' -Name AppCompatCache -ErrorAction Stop).AppCompatCache}catch{}
$b64='';$n=0;try{$b=[byte[]]$v;$n=$b.Length;if($n -gt 16384){$b=$b[0..16383]};$b64=[Convert]::ToBase64String($b)}catch{}
[pscustomobject]@{skill='appcompat';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');blob_bytes=$n;truncated=($n -gt 16384);blob_b64=$b64}|ConvertTo-Json -Compress
