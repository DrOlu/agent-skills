# krb — Kerberos abuse on a domain controller. Watch-only, capped, one JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList; $MsgCap
#
# Reads the DC's Security log for the Kerberos attack surface:
#   4768 TGT issued (AS-REQ)   — AS-REP roast candidates, spray volume
#   4769 TGS issued (TGS-REQ)  — Kerberoasting (RC4 etype 0x17), SPN spray
#   4771 Kerberos pre-auth failed — password spray at the KDC
#   4776 NTLM credential validation (fallback / downgrade signal)
# Collapsed per (principal,spn,etype) to counts: a spray is one row, not 10k.
# NOT a domain dump. NOT the whole Kerberos log.
$since=(Get-Date).AddHours(-[double]$SinceHours)
$Max=[int]$Limit*20
function F($ev,$n){$x=[xml]$ev.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function A($t,$n,$v){if($v){$script:o+=@([pscustomobject]@{t=$t;n=$n;c=@($v).Count;v=@($v|select -First 10)})}}
$script:o=@()

# --- 4768: TGT issued. Track pre-auth disabled (AS-REP roast) + spray volume ---
try{
  $g=@{}
  Get-WinEvent -FilterHashtable @{LogName='Security';Id=4768;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    $u=F $_ 'TargetUserName'; $ip=F $_ 'IpAddress'; $k="$u|$ip"
    if(-not $g.ContainsKey($k)){$g[$k]=[pscustomobject]@{user=$u;src=$ip;n=0;nopre=0;last=''}}
    $g[$k].n++
    if((F $_ 'PreAuthType') -eq '0'){$g[$k].nopre++}
    $t=$_.TimeCreated.ToString('o'); if($t -gt $g[$k].last){$g[$k].last=$t}
  }
  A 'tgt' 'issued' @($g.Values|Sort-Object n -Descending|select -First $Limit)
  A 'tgt' 'no-pre-auth (AS-REP roastable)' @($g.Values|Where-Object{$_.nopre -gt 0}|select -First $Limit)
}catch{}

# --- 4769: TGS issued. Kerberoasting = RC4 (0x17) TGS for service accounts ---
try{
  $g=@{}
  Get-WinEvent -FilterHashtable @{LogName='Security';Id=4769;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    $u=F $_ 'TargetUserName'; $spn=F $_ 'ServiceName'; $et=F $_ 'TicketEncryptionType'; $k="$u|$spn|$et"
    if(-not $g.ContainsKey($k)){$g[$k]=[pscustomobject]@{user=$u;spn=$spn;etype=$et;n=0;last=''}}
    $g[$k].n++
    $t=$_.TimeCreated.ToString('o'); if($t -gt $g[$k].last){$g[$k].last=$t}
  }
  A 'tgs' 'issued' @($g.Values|Sort-Object n -Descending|select -First $Limit)
  A 'tgs' 'rc4 (roastable, 0x17)' @($g.Values|Where-Object{$_.etype -eq '0x17'}|select -First $Limit)
}catch{}

# --- 4771: pre-auth failures (spray at KDC) + 4776 NTLM validation ---
try{$p=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4771;StartTime=$since} -MaxEvents $Max|ForEach-Object{
  [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'TargetUserName');src=(F $_ 'IpAddress');code=(F $_ 'Status')}
})}catch{$p=@()}
try{$n=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4776;StartTime=$since} -MaxEvents $Max|ForEach-Object{
  [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'TargetUserName');src=(F $_ 'Workstation')}
})}catch{$n=@()}

$tgt=@($script:o|Where-Object{$_.t -eq 'tgt'})
$tgs=@($script:o|Where-Object{$_.t -eq 'tgs'})
[pscustomobject]@{
  skill='krb';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o')
  tgt=$tgt;tgs=$tgs
  preauth_fail=@($p|select -First $Limit);ntlm_validate=@($n|select -First $Limit)
}|ConvertTo-Json -Compress -Depth 5
