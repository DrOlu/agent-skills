# flowstats — per-destination byte counts + adapter volume, for T1041 (exfiltration) detection.
#
# The gap this closes: exfiltration is detectable from METADATA + BASELINES, not payloads.
# Sysmon EID 3 already gives destination/port/process. What it doesn't give is BYTES.
# This question returns:
#   - per-adapter sent/received totals (the volume baseline the thinker needs)
#   - per-remote-address connection counts + owning processes (who is talking where)
#   - top talkers by connection count
#
# Kilobytes. No packet capture. No payload. The 32 KB cap holds.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$adapters=@()
try{$adapters=@(Get-NetAdapterStatistics -ErrorAction SilentlyContinue|ForEach-Object{
 [pscustomobject]@{name=$_.Name;sent=$_.SentBytes;recv=$_.ReceivedBytes}
})}catch{}
$conns=@()
try{
 $owned=@{}
 foreach($p in (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)){$o=$p.GetOwner().User; if($Track -contains $o){$owned[$p.ProcessId]=$p.Name}}
 $conns=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue|Where-Object{$_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)'}|Group-Object RemoteAddress|Sort-Object Count -Descending|Select-Object -First $Limit|ForEach-Object{
  $procs=($_.Group|Select-Object -ExpandProperty OwningProcess -Unique|ForEach-Object{$owned[$_]}|Where-Object{$_}) -join ','
  [pscustomobject]@{dest=$_.Name;conns=$_.Count;ports=($_.Group|Select-Object -ExpandProperty RemotePort -Unique|Select-Object -First 5) -join ',';procs=$procs}
 })
}catch{}
$udp=@()
try{$udp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue|Where-Object{$_.RemoteAddress -and $_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)'}|Group-Object RemoteAddress|Sort-Object Count -Descending|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{dest=$_.Name;endpoints=$_.Count}
})}catch{}
[pscustomobject]@{skill='flowstats';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');track=$Track;adapters=@($adapters);top_destinations=@($conns);udp_endpoints=@($udp)}|ConvertTo-Json -Compress -Depth 4
