# Allowlisted: who did Administrator/SYSTEM touch since $SinceHours. Capped. No full table.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# REV 2 (2026-08-19): +4648 explicit creds (lateral movement), +4672 special privs.
# REV 16: +4625 tracked failures, collapsed to DISTINCT SOURCES (count + last seen +
#   substatus), same join shape as successes. A brute force is one row per source IP,
#   not 76 rows a minute — the cap survives, the lake never forms. This closes the
#   "smoke with no pointer" hole: the 95.142.115.135 attack hit Administrator, not the
#   canary, so the observatory could count but not name the client. block_ip needs a name.
function F($ev,$name){
  $x=[xml]$ev.ToXml();$ns=New-Object System.Xml.XmlNamespaceManager($x.NameTable)
  $ns.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event')
  $n=$x.SelectSingleNode("//e:Data[@Name='$name']",$ns); if($n){$n.'#text'} else {$null}
}
# REV 17 (L4): exact bare-name match — a substring match on SYSTEM also lit
# up SYSTEMBACKUP. REV 17 (M1): -MaxEvents on every Get-WinEvent so a flood
# cannot balloon the scan past ASK_TIMEOUT; the device sheds first.
function TT($ev){$t=F $ev 'TargetUserName';if($t){$b=($t -split '\\')[-1];foreach($tr in $Track){if($b -eq $tr){return $true}}};return $false}
$since=(Get-Date).AddHours(-$SinceHours)
$M=[int]$Limit*20

# --- 4624 tracked logons (src IP, logon id, auth package) ---
$logons=@()
try{$logons=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$since} -MaxEvents $M|? TT|select -First $Limit|%{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'TargetUserName');type=(F $_ 'LogonType');src=(F $_ 'IpAddress');lid=(F $_ 'TargetLogonId');auth=(F $_ 'AuthenticationPackageName')}
})}catch{}

# --- REV 16: 4625 tracked failures, DISTINCT-SOURCE collapse ---
# One row per (src,user): count + last-seen + substatus. Substatus tells
# wrong-pw (0xc000006a) from disabled (0xc0000072) from locked (0xc0000234).
# A spray is ONE row, not 76/min — cap survives, no lake. Capped at $Limit.
$failed=@()
try{
 $g=@{}
 Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$since} -MaxEvents $M|? TT|%{
  $i=F $_ 'IpAddress';$u=F $_ 'TargetUserName';$k="$i|$u"
  if(-not $g.ContainsKey($k)){$g[$k]=[pscustomobject]@{user=$u;src=$i;type=(F $_ 'LogonType');auth=(F $_ 'AuthenticationPackageName');n=0;last='';sub=(F $_ 'SubStatus')}}
  $g[$k].n++
  $t=$_.TimeCreated.ToString('o');if($t -gt $g[$k].last){$g[$k].last=$t}
 }
 $failed=@($g.Values|sort n -Descending|select -First $Limit)
}catch{}

# --- 4648 explicit credentials (runas / -Credential / Invoke-Command) ---
$explicit=@()
try{$explicit=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4648;StartTime=$since} -MaxEvents $M|? TT|select -First $Limit|%{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');who=(F $_ 'SubjectUserName');became=(F $_ 'TargetUserName');dest=(F $_ 'TargetServerName');src=(F $_ 'IpAddress')}
})}catch{}

# --- 4672 special privileges (privilege set matters: SeDebugPrivilege, SeTcbPrivilege) ---
$privs=@()
try{$privs=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4672;StartTime=$since} -MaxEvents $M|? TT|select -First $Limit|%{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'SubjectUserName');src=(F $_ 'IpAddress');privs=((F $_ 'PrivilegeList') -replace '\s+',',')}
})}catch{}

# --- outbound remote connections owned by SYSTEM/Administrator processes ---
$conns=@()
try{
 $owned=@{}
 # BUG FIX (rev 14): .GetOwner().User returns '' on Server 2022 via WinRM —
 # conns were silently empty. Invoke-CimMethod works; match bare name suffix.
 foreach($p in (Get-CimInstance Win32_Process)){
   $o=Invoke-CimMethod -InputObject $p -MethodName GetOwner
   $u=$o.User
   if($u -and ($Track -contains ($u -split '\\')[-1])){$owned[$p.ProcessId]=$p.Name}
 }
 $conns=@(Get-NetTCPConnection -State Established|Where-Object{$_.RemoteAddress -notmatch '^(127\.|0\.0\.0\.0|::|::1)' -and $owned.ContainsKey($_.OwningProcess)}|select -First $Limit|%{
  [pscustomobject]@{dest=$_.RemoteAddress;port=$_.RemotePort;pid=$_.OwningProcess;proc=$owned[$_.OwningProcess]}
 })
}catch{}

[pscustomobject]@{skill='edges';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;logons=@($logons);failed_sources=@($failed);explicit_creds=@($explicit);special_privs=@($privs);conns=@($conns)}|ConvertTo-Json -Compress -Depth 4