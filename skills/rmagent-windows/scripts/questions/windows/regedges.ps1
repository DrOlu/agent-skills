# regedges — path-allowlisted Sysmon 13 (Registry value set) for tracked principals.
# Watch-only. Photograph of WHO turned a known latch — not a hive dump, not a write.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function MT($u){ if(-not $u){return $false}; foreach($t in $Track){ if((($u -split '\\')[-1]) -eq $t){return $true} }; return $false }
$need=@('\CurrentVersion\Run','Image File Execution Options','AppCertDlls','AppInit_DLLs','\Control\Lsa','\Winlogon','\Microsoft\Netsh','Print\Monitors','UserInitMprLogonScript','SilentProcessExit','SafeBoot','CurrentControlSet\Services')
function PK($p){ if(-not $p){return $false}; foreach($n in $need){ if($p -like "*$n*"){return $true} }; return $false }
$since=(Get-Date).AddHours(-$SinceHours)
$sets=@(); $n13=0; $st='absent'; $sm='unknown'
try{$s=Get-Service Sysmon*,Sysmon64 -EA SilentlyContinue|select -First 1; if($s){$sm=[string]$s.Status}else{$sm='not-installed'}}catch{}
try {
  $ev=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational';Id=13;StartTime=$since} -EA Stop | Select-Object -First ([Math]::Min($Limit,80)))
  $n13=$ev.Count
  $st= if($n13 -gt 0){'ok'}else{'blind'}
  $sets=@($ev | Where-Object { (MT (F $_ 'User')) -and (PK (F $_ 'TargetObject')) } | Select-Object -First $Limit | ForEach-Object {
    $d=F $_ 'Details'; if($d -and $d.Length -gt 80){$d=$d.Substring(0,80)}
    [pscustomobject]@{t=$_.TimeCreated.ToString('o');proc=(F $_ 'Image');user=(F $_ 'User');key=(F $_ 'TargetObject');val=$d}
  })
} catch { $st='absent' }
if($st -eq 'blind' -and $sm -ne 'Running'){$st='absent'}
[pscustomobject]@{skill='regedges';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;sysmon=$sm;sysmon_reg=$st;raw_13=$n13;sets=@($sets)}|ConvertTo-Json -Compress -Depth 4
