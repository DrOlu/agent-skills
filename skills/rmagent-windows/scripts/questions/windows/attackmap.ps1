# attackmap — ATT&CK persistence STATE. Read-only, capped. ONE JSON.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$H='HKLM:';$U='HKCU:';$R='\SOFTWARE\Microsoft\Windows\CurrentVersion\Run';$W='\SOFTWARE\Microsoft\Windows NT\CurrentVersion';$L='\SYSTEM\CurrentControlSet\Control\Lsa'
$o=@()
function A($t,$n,$v){if($v){$script:o+=@([pscustomobject]@{t=$t;n=$n;c=@($v).Count;v=@($v|Select -First 8)})}}
function RK($p){$r=@();try{$k=Get-ItemProperty -Path $p -EA SilentlyContinue;if($k){$r=@($k.PSObject.Properties|?{$_.Name -notmatch '^PS'}|%{"$($_.Name)=$($_.Value)"})}}catch{};$r}
function RV($p,$n){try{(Get-ItemProperty -Path $p -Name $n -EA SilentlyContinue).$n}catch{}}
A 'T1547.001' 'run_keys' (@(RK "$H$R")+@(RK "$H$R`Once")+@(RK "$U$R")+@(RK 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'))
$if=@();try{Get-ChildItem "$H$W\Image File Execution Options" -EA SilentlyContinue|%{$d=(Get-ItemProperty $_.PSPath -Name Debugger -EA SilentlyContinue).Debugger;if($d){$if+="$($_.PSChildName)->$d"}}}catch{}
A 'T1546.010' 'ifeo_dbg' $if
A 'T1546.009' 'appcert' (RK 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\AppCertDlls')
A 'T1546.010' 'appinit' (@(RV "$H$W\Windows" 'AppInit_DLLs')|?{$_})
A 'T1547.005' 'ssp' (@(RV "$H$L" 'SecurityPackages'))
A 'T1547.002' 'authpkg' (@(RV "$H$L" 'NotificationPackages'))
A 'T1547.004' 'winlogon' (@((RV "$H$W\Winlogon" 'Userinit')|?{$_ -and $_ -notmatch 'userinit'})+@((RV "$H$W\Winlogon" 'Shell')|?{$_ -and $_ -notmatch 'explorer'}))
A 'T1546.007' 'netsh' (RK 'HKLM:\SOFTWARE\Microsoft\Netsh')
$pm=@();try{Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors' -EA SilentlyContinue|%{$d=RV $_.PSPath 'Driver';if($d){$pm+="$($_.PSChildName)->$d"}}}catch{}
A 'T1547.010' 'portmon' $pm
A 'T1037.001' 'logonscript' (@(RV "$U\Environment" 'UserInitMprLogonScript')|?{$_})
A 'T1547.001' 'runonce' (@(RK "$H$R`Once")+@(RK "$U$R`Once"))
$sp=@();try{Get-ChildItem "$H$W\SilentProcessExit" -EA SilentlyContinue|%{$m=RV $_.PSPath 'MonitorProcess';if($m){$sp+="$($_.PSChildName)->$m"}}}catch{}
A 'T1546.012' 'silent_exit' $sp
A 'T1547.001' 'cmd_autorun' (@(RV "$H\SOFTWARE\Microsoft\Command Processor" 'AutoRun')+@(RV "$U\SOFTWARE\Microsoft\Command Processor" 'AutoRun')|?{$_})
$ac=@();try{Get-LocalUser -EA SilentlyContinue|?{$_.WhenCreated -gt (Get-Date).AddDays(-7)}|%{$ac+=$_.Name}}catch{}
A 'T1136.001' 'new_acct' $ac
$fw=@();try{Get-NetFirewallProfile -EA SilentlyContinue|?{!$_.Enabled}|%{$fw+="$($_.Name):off"}}catch{}
A 'T1562.004' 'fw_off' $fw
[pscustomobject]@{skill='attackmap';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');track=$Track;checked=16;found=$script:o.Count;findings=@($script:o)}|ConvertTo-Json -Compress -Depth 5
