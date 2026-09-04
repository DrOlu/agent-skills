# dns — DNS covert-channel signals from the Sysmon EID 22 ring (T1071.004).
# Long labels, high-entropy names, unusual TLDs, volume to one domain.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$long=@(); $entropic=@(); $tlds=@(); $vol=@(); $n=0
try{$evs=Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational';Id=22;StartTime=$cutoff} -MaxEvents 500 -EA SilentlyContinue
$n=@($evs).Count
$domCount=@{}
foreach($e in $evs){
  $x=[xml]$e.ToXml()
  $q=($x.Event.EventData.Data|?{$_.Name -eq 'QueryName'}).'#text'
  if(-not $q){continue}
  $q=$q.TrimEnd('.')
  # volume per domain
  $domCount[$q]=1+($domCount[$q] | ForEach-Object { if($_){$_}else{0} })
  # long labels (>40 chars in a single label = tunneling)
  $labels=$q -split '\.'
  foreach($l in $labels){if($l.Length -gt 40){
    $long+=[pscustomobject]@{domain=$q;label_len=$l.Length;t=$e.TimeCreated.ToString('o')};break}}
  # high entropy: hex/base64-looking labels >= 20 chars
  if($q -match '[a-f0-9]{20,}' -or $q -match '[A-Za-z0-9+/=]{25,}'){
    $entropic+=[pscustomobject]@{domain=$q;t=$e.TimeCreated.ToString('o')}}
  # unusual TLDs (cheap list — not exhaustive, deliberately)
  if($q -match '\.(xyz|top|gq|tk|ml|cf|cn|ru|su|work|click|link|zip|mov)$'){
    $tlds+=[pscustomobject]@{domain=$q;t=$e.TimeCreated.ToString('o')}}
}
# top domains by volume
$vol=@($domCount.GetEnumerator()|Sort-Object Value -Descending|Select -First $Limit|%{
  [pscustomobject]@{domain=$_.Key;count=$_.Value}})
}catch{}
$long=@($long|Select -First $Limit); $entropic=@($entropic|Select -First $Limit); $tlds=@($tlds|Select -First $Limit)
[pscustomobject]@{skill='dns';host=$hn;utc=$now;window_h=$sh;n_dns_events=$n;n_long_labels=@($long).Count;long_labels=$long;n_entropic=@($entropic).Count;entropic=$entropic;n_unusual_tld=@($tlds).Count;unusual_tld=$tlds;top_domains=$vol}|ConvertTo-Json -Compress -Depth 4