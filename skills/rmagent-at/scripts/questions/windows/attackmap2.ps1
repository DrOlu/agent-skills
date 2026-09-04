# attackmap2 — ATT&CK persistence map part 2 (12 more techniques).
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$o=@()
function A($t,$n,$v){if($v){$script:o+=@([pscustomobject]@{t=$t;n=$n;c=$v.Count;v=@($v|select -First 10)})}}
function RK($p){$r=@();try{$k=Get-ItemProperty -Path $p -EA SilentlyContinue;if($k){$r=@($k.PSObject.Properties|?{$_.Name -notmatch '^PS'}|%{"$($_.Name)=$($_.Value)"})}}catch{};return $r}
function RV($p,$n){try{(Get-ItemProperty -Path $p -Name $n -EA SilentlyContinue).$n}catch{}}
$st=@();try{Get-ScheduledTask -EA SilentlyContinue|?{$_.State -ne 'Disabled' -and $_.TaskPath -notlike '\Microsoft*'}|select -First 15|%{$st+=$_.TaskName}}catch{}
A 'T1053.005' 'schtasks' $st
$sv=@();try{Get-CimInstance Win32_Service -EA SilentlyContinue|?{$_.State -eq 'Running' -and $_.PathName -notmatch '(?i)\\Windows\\|\\Program Files'}|select -First 12|%{$sv+=$_.Name}}catch{}
A 'T1543.003' 'svc_persist' $sv
$wm=@();try{Get-WmiObject -Namespace root\subscription -Class __EventFilter -EA SilentlyContinue|select -First 6|%{$wm+=$_.Name}}catch{}
A 'T1546.003' 'wmi_sub' $wm
$sf=@();try{foreach($p in @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup")){if(Test-Path $p){Get-ChildItem $p -EA SilentlyContinue|%{$sf+=$_.Name}}}}catch{}
A 'T1547.001' 'startup' $sf
$co=@();try{Get-ChildItem 'HKCU:\Software\Classes\CLSID' -Depth 1 -EA SilentlyContinue|select -First 20|%{$d=RV $_.PSPath 'InprocServer32';if($d -and $d -notmatch '(?i)\\Windows\\|\\Program Files'){$co+=$_.PSChildName}}}catch{}
A 'T1546.008' 'com_hijack' $co
$tk=@();foreach($v in @('__PSLockdownPolicy','PSTokenPath')){$x=[Environment]::GetEnvironmentVariable($v);if($x){$tk+="$v"}}
A 'T1134' 'token_env' $tk
A 'T1547.014' 'runonceex' (RK "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnceEx")
$lk=@();try{Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" -Filter *.lnk -EA SilentlyContinue|?{$_.LastWriteTime -gt (Get-Date).AddDays(-7)}|select -First 6|%{$lk+=$_.Name}}catch{}
A 'T1547.009' 'shortcut' $lk
$ls=@();try{Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Group Policy\Scripts' -EA SilentlyContinue|select -First 6|%{$ls+=$_.PSChildName}}catch{}
A 'T1547.015' 'gpo_script' $ls
$dl=@();try{$c=(Get-Location).Path;foreach($f in @('version.dll','sqlite3.dll')){if(Test-Path "$c\$f"){$dl+=$f}}}catch{}
A 'T1574.001' 'dll_search' $dl
$se=@();try{Get-ChildItem 'HKCU:\Software\Classes\*\shellex\CtxHandlers' -EA SilentlyContinue|select -First 6|%{$se+=$_.PSChildName}}catch{}
A 'T1546.011' 'shellext' $se
$bi=@();try{Get-WinEvent -LogName 'Microsoft-Windows-Bits-Client/Operational' -MaxEvents 20 -EA SilentlyContinue|?{$_.Id -eq 3}|select -First 3|%{$bi+=$_.Message.Substring(0,40)}}catch{}
A 'T1197' 'bitsadmin' $bi
[pscustomobject]@{skill='attackmap2';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');track=$Track;checked=12;found=$o.Count;findings=@($o)}|ConvertTo-Json -Compress -Depth 5