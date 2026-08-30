# lineage — process-lineage joins from the Sysmon EID 1 ring (process create).
# Closes the biggest TTP gap: macro delivery, phishing spawn, LOLBin chains.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$P='winword.exe|excel.exe|outlook.exe|powerpnt.exe|wscript.exe|cscript.exe|mshta.exe|wmiprvse.exe|taskeng.exe|schtasks.exe|rundll32.exe|regsvr32.exe|certutil.exe|bitsadmin.exe|java.exe|javaw.exe'
$C='powershell|cmd.exe|wscript|cscript|mshta|rundll32|regsvr32|certutil|bitsadmin|msiexec|wmic|netsh|curl'
$hits=@(); $lol=@(); $n=0
$evs=$null
try{$evs=Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Sysmon/Operational';Id=1;StartTime=$cutoff} -EA SilentlyContinue|Select -First 300}catch{}
if($evs){
  $n=@($evs).Count
  foreach($e in $evs){
    try{
      $x=[xml]$e.ToXml()
      $img=($x.Event.EventData.Data|?{$_.Name -eq 'Image'}).'#text'
      $par=($x.Event.EventData.Data|?{$_.Name -eq 'ParentImage'}).'#text'
      $usr=($x.Event.EventData.Data|?{$_.Name -eq 'User'}).'#text'
      $cmd=($x.Event.EventData.Data|?{$_.Name -eq 'CommandLine'}).'#text'
      if(-not $img){continue}
      $il=$img.ToLower(); $pl=($(if($par){$par}else{''})).ToLower()
      if($pl -match $P -and $il -match $C){
        $hits+=[pscustomobject]@{parent=$par;child=$img;user=$usr;cmd=($(if($cmd){$cmd}else{''})).Substring(0,[Math]::Min(70,($(if($cmd){$cmd}else{''})).Length))}
      }
      if($usr -and $il -match $C){
        foreach($t in $Track){
          if($usr -like "*$t*"){
            $lol+=[pscustomobject]@{proc=$img;user=$usr}
            break
          }
        }
      }
    }catch{}
  }
}
$hits=@($hits|Select -First $Limit)
$lol=@($lol|Select -First $Limit)
[pscustomobject]@{skill='lineage';host=$hn;utc=$now;window_h=$sh;n_proc_events=$n;n_pairs=@($hits).Count;pairs=$hits;n_tracked_lol=@($lol).Count;tracked_lol=$lol}|ConvertTo-Json -Compress -Depth 4