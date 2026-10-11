# vol — process volatility triage. Snapshot + suspicious indicators.
# Flag rules: parent dead (orphan), or path under user-writable dirs, or
# system-dir name running from elsewhere. No agent, no driver — built-ins only.
$T=140
$procs=@();try{$procs=@(Get-CimInstance Win32_Process)}catch{}
$byid=@{};foreach($p in $procs){$byid[[int]$p.ProcessId]=$p}
$susp=@();$top=@()
foreach($p in $procs){
  $cl='';if($p.CommandLine){$cl=($p.CommandLine -replace '\s+',' ');if($cl.Length -gt $T){$cl=$cl.Substring(0,$T)+'…'}}
  $nm=$p.Name;$pp=$null
  try{if($p.ParentProcessId){$pp=$byid[[int]$p.ParentProcessId]}}catch{}
  $orphan=($null -eq $pp -and $p.ParentProcessId -gt 4)
  $low='';if($p.ExecutablePath){$low=$p.ExecutablePath.ToLower()}
  $writable=($low -match '\\users\\|\\temp\\|\\appdata\\|\\programdata\\|\\public\\') -and ($low -notmatch '\\windows\\')
  $masq=($nm -in @('svchost.exe','lsass.exe','csrss.exe','services.exe','winlogon.exe','smss.exe') -and $low -and ($low -notmatch '^c:\\windows\\'))
  $why=@();if($orphan){$why+='orphan'};if($writable){$why+='user-writable-path'};if($masq){$why+='masquerade'}
  if($why.Count -gt 0){$susp+=[pscustomobject]@{pid=$p.ProcessId;name=$nm;path=$p.ExecutablePath;cmd=$cl;why=($why -join '+')}}
  if($top.Count -lt $Limit){$top+=[pscustomobject]@{pid=$p.ProcessId;ppid=$p.ParentProcessId;name=$nm;cmd=$cl;start=$(if($p.CreationDate){$p.CreationDate.ToString('o')}else{''})}}
}
# lsass module sanity: count non-Microsoft modules inside lsass
$lmod=-1;try{$lp=Get-Process lsass -ErrorAction Stop;$lmod=@($lp.Modules|?{$_.FileName -notmatch '^C:\\Windows\\'}).Count}catch{}
[pscustomobject]@{skill='vol';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');count=$procs.Count;lsass_foreign_modules=$lmod;suspicious_count=$susp.Count;suspicious=$susp;processes=$top}|ConvertTo-Json -Compress -Depth 4
