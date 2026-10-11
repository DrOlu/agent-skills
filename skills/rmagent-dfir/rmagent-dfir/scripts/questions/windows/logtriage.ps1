# logtriage — Security log digest. Positional .Properties access (fast);
# counts for critical IDs, failed-logon top users/sources, notable rows.
$ids=4624,4625,4648,4672,4688,4698,7045,4720,4726,4732,1102
$sn=(Get-Date).ToUniversalTime().AddHours(-$SinceHours)
$ev=@();try{$ev=@(Get-WinEvent -FilterHashtable @{LogName='Security';StartTime=$sn} -MaxEvents 2500 -ErrorAction Stop)}catch{}
$cts=@{};foreach($i in $ids){$cts[[string]$i]=@($ev|?{$_.Id -eq $i}).Count}
$f5=@();foreach($x in ($ev|?{$_.Id -eq 4625}|Select -First 800)){$p=$x.Properties;$f5+=[pscustomobject]@{u=[string]$p[5].Value;ip=[string]$p[19].Value}}
$ub=@();$ib=@();foreach($g in ($f5|Group-Object u|Sort Count -Desc|Select -First 5)){$ub+=[pscustomobject]@{user=$g.Name;count=$g.Count}}
foreach($g in ($f5|Group-Object ip|Sort Count -Desc|Select -First 5)){$ib+=[pscustomobject]@{source=$g.Name;count=$g.Count}}
$ns=@();foreach($x in ($ev|?{$_.Id -eq 7045}|Select -First $Limit)){$p=$x.Properties;$ns+=[pscustomobject]@{n=[string]$p[0].Value;p=[string]$p[1].Value;t=$x.TimeCreated.ToString('o')}}
$ac=@();foreach($x in ($ev|?{$_.Id -in 4720,4726,4732}|Select -First $Limit)){$p=$x.Properties;$k='user-deleted';if($x.Id -eq 4720){$k='user-created'};if($x.Id -eq 4732){$ac+=[pscustomobject]@{k='group-add';group=[string]$p[0].Value;member=[string]$p[1].Value;t=$x.TimeCreated.ToString('o')}}
if($x.Id -in 4720,4726){$k='user-deleted';if($x.Id -eq 4720){$k='user-created'};$ac+=[pscustomobject]@{k=$k;user=[string]$p[0].Value;t=$x.TimeCreated.ToString('o')}}}
$clr=@($ev|?{$_.Id -eq 1102}).Count
[pscustomobject]@{skill='logtriage';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');hours=$SinceHours;total=$ev.Count;counts=$cts;failed_users=$ub;failed_sources=$ib;new_services=$ns;account_events=$ac;audit_cleared=$clr}|ConvertTo-Json -Compress -Depth 5
