# dcsync — directory replication abuse (DCSync / DCShadow / DRS rights). One JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList; $MsgCap
#
# DCSync = an account asks a DC to replicate secrets over DRSUAPI, without
# touching the DC's disk. On the DC it appears as 4662 (object access on the
# domain NC) with the replication-control access masks, by a non-DC principal.
#   4662   — DS object access (replication GUIDs)
#   4624   — type 3 logon by the replicating principal (context)
#   5136   — directory service changes (DCShadow persistence)
# Collapsed per (principal,access-mask) to counts. NOT the whole directory log.
$since=(Get-Date).AddHours(-[double]$SinceHours)
$Max=[int]$Limit*20
function F($ev,$n){$x=[xml]$ev.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
# Replication rights GUIDs registered in AD (schema). Presence is the tell.
$REPL_GUIDS='1131f6aa-9c07-11d1-f79f-00c04fc2dcd2','1131f6ad-9c07-11d1-f79f-00c04fc2dcd2','89e95b76-444d-4c62-991a-0facbeda640c','1131f6ab-9c07-11d1-f79f-00c04fc2dcd2'

# --- 4662 by a non-DC principal touching replication rights ---
$repl=@(); $dcsh=@()
try{
  $g=@{}
  Get-WinEvent -FilterHashtable @{LogName='Security';Id=4662;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    $acc=F $_ 'AccessMask'; $props=[string](F $_ 'Properties'); $subj=F $_ 'SubjectUserName'
    $hasRepl=$false; foreach($r in $REPL_GUIDS){ if($props -match $r){$hasRepl=$true} }
    if($hasRepl){
      $k="$subj|$acc"
      if(-not $g.ContainsKey($k)){$g[$k]=[pscustomobject]@{subject=$subj;access_mask=$acc;n=0;last='';props=($props.Substring(0,[Math]::Min($MsgCap,$props.Length)))}} 
      $g[$k].n++; $t=$_.TimeCreated.ToString('o'); if($t -gt $g[$k].last){$g[$k].last=$t}
    }
  }
  $repl=@($g.Values|Sort-Object n -Descending|select -First $Limit)
}catch{}

# --- 5136: directory service changes by a tracked principal (DCShadow) ---
try{$dcsh=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=5136;StartTime=$since} -MaxEvents $Max|ForEach-Object{
  $subj=F $_ 'SubjectUserName'
  if($subj -and ($Track -contains ($subj -split '\\')[-1])){ [pscustomobject]@{t=$_.TimeCreated.ToString('o');who=$subj;attr=(F $_ 'AttributeLDAPDisplayName')} }
}|Where-Object{$_}|select -First $Limit)}catch{}

# --- 4624 type 3 context for the principals we saw replicating ---
$subjects=@($repl|ForEach-Object{$_.subject}|select -Unique)
$logonctx=@()
if($subjects.Count){
  try{$logonctx=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    $u=F $_ 'TargetUserName'; $lt=F $_ 'LogonType'
    if($u -and ($subjects -contains $u) -and $lt -eq '3'){ [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=$u;src=(F $_ 'IpAddress');lid=(F $_ 'TargetLogonId')} }
  }|Where-Object{$_}|select -First $Limit)}catch{}
}

[pscustomobject]@{
  skill='dcsync';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o')
  replication_access=@($repl);dir_changes=@($dcsh);logon_context=@($logonctx)
  note='replication_access rows mean a principal used DRS replication rights (DCSync) — DCSync from a non-DC account is the finding'
}|ConvertTo-Json -Compress -Depth 5
