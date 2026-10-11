# conn — live connections with owning process. External = non-RFC1918,
# non-link-local, not loopback. Loopback pairs are counted, not listed (budget).
$T=140
$rows=@();try{$rows=@(Get-NetTCPConnection -State Established,Bound -ErrorAction Stop)}catch{}
$pn=@{};try{Get-Process|foreach{$pn[$_.Id]=$_.Path}}catch{}
$ext=@();$pairs=0;$list=0
foreach($r in $rows){
  $proc='';try{$proc=Split-Path -Leaf $pn[[int]$r.OwningProcess]}catch{}
  $ra=$r.RemoteAddress
  if($ra -eq '127.0.0.1' -or $ra -eq '::1'){$pairs++;continue}
  $isExt=-not ($ra -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.|fe80|::1)')
  if($isExt -and $list -lt $Limit){$list++;$path=$pn[[int]$r.OwningProcess];if($path.Length -gt $T){$path=$path.Substring(0,$T)+'…'}
    $ext+=[pscustomobject]@{local="$($r.LocalAddress):$($r.LocalPort)";remote="$ra`:$($r.RemotePort)";state=$r.State;pid=$r.OwningProcess;proc=$proc;path=$path}}
}
$udp=0;try{$udp=@(Get-NetUDPEndpoint).Count}catch{}
[pscustomobject]@{skill='conn';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');tcp_rows=$rows.Count;loopback_pairs=$pairs;udp_endpoints=$udp;external_count=$ext.Count;external=$ext}|ConvertTo-Json -Compress -Depth 4
