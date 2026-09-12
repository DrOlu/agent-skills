# dirchange — privileged directory changes on a DC. One JSON object, watch-only.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList; $MsgCap
#
# The domain-level privilege events a member-server view cannot see:
#   4720/4726  account created / deleted        — rogue identities
#   4728/4732/4756  member added to a privileged group (domain/local/universal)
#   4729/4733/4757  member removed
#   4740       account lockout
#   1102       audit policy changed (someone turned off the lights)
# Limited to the privileged groups that matter; collapsed to counts. NOT a dump.
$since=(Get-Date).AddHours(-[double]$SinceHours)
$Max=[int]$Limit*20
function F($ev,$n){$x=[xml]$ev.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
$PRIV=@('Domain Admins','Enterprise Admins','Administrators','Schema Admins','Account Operators','Backup Operators','Server Operators','Group Policy Creator Owners','DNSAdmins','Protected Users')

$added=@();$created=@();$deleted=@();$lockout=@();$audit=@()
foreach($id in @(4728,4732,4756)){
  try{ $added+=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=$id;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    $grp=F $_ 'TargetUserName'; $mbr=F $_ 'MemberName'; $by=F $_ 'SubjectUserName'
    if($grp -and ($PRIV -contains $grp)){ [pscustomobject]@{t=$_.TimeCreated.ToString('o');eid=$id;group=$grp;member=$mbr;by=$by} }
  }|Where-Object{$_}) }catch{}
}
foreach($id in @(4720)){
  try{ $created+=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=$id;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    [pscustomobject]@{t=$_.TimeCreated.ToString('o');new_account=(F $_ 'TargetUserName');by=(F $_ 'SubjectUserName')}
  }) }catch{}
}
foreach($id in @(4726)){
  try{ $deleted+=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=$id;StartTime=$since} -MaxEvents $Max|ForEach-Object{
    [pscustomobject]@{t=$_.TimeCreated.ToString('o');deleted=(F $_ 'TargetUserName');by=(F $_ 'SubjectUserName')}
  }) }catch{}
}
try{ $lockout=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;StartTime=$since} -MaxEvents $Max|ForEach-Object{
  [pscustomobject]@{t=$_.TimeCreated.ToString('o');user=(F $_ 'TargetUserName');src=(F $_ 'TargetDomainName')}
} |Select -First $Limit) }catch{}
try{ $audit=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=1102;StartTime=$since} -MaxEvents $Limit|ForEach-Object{
  [pscustomobject]@{t=$_.TimeCreated.ToString('o');by=(F $_ 'SubjectUserName')}
}) }catch{}

[pscustomobject]@{
  skill='dirchange';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o')
  priv_group_adds=@($added|select -First $Limit);accounts_created=@($created|select -First $Limit)
  accounts_deleted=@($deleted|select -First $Limit);lockouts=@($lockout);audit_cleared=@($audit)
  n_priv_adds=$added.Count;n_created=$created.Count;n_deleted=$deleted.Count;n_lockouts=$lockout.Count;n_audit_cleared=$audit.Count
}|ConvertTo-Json -Compress -Depth 5
