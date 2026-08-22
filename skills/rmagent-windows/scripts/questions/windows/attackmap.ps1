# attackmap — ATT&CK-mapped persistence STATE check (registry locations from
# BLUESPAWN's hunt registry, reimplemented pull-only). Catches persistence that
# ALREADY EXISTS — predates our monitoring window. Each finding carries its ATT&CK ID.
# Note: services + scheduled tasks are caught by explain (events) and sketch —
# attackmap focuses on the REGISTRY persistence locations events never show.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$H='HKLM:\';$U='HKCU:\'
$R="SOFTWARE\Microsoft\Windows\CurrentVersion\Run";$L="SYSTEM\CurrentControlSet\Control\Lsa"
$W="SOFTWARE\Microsoft\Windows NT\CurrentVersion"
function RV($p,$n){try{(Get-ItemProperty -Path $p -Name $n -ErrorAction SilentlyContinue).$n}catch{}}
function RK($p){try{$k=Get-ItemProperty -Path $p -ErrorAction SilentlyContinue;if($k){@($k.PSObject.Properties|Where-Object{$_.Name -notmatch '^PS'}|ForEach-Object{"$($_.Name)=$($_.Value)"})}else{@()}}catch{@}}
$o=@()
function A($t,$n,$v){$v=@($v|Where-Object{$_ -ne $null -and $_ -ne ''});if($v.Count){$o+=[pscustomobject]@{t=$t;n=$n;c=$v.Count;v=@($v|Select-Object -First $Limit)}}}
A 'T1547.001' 'run_keys' (@(RK "$H$R")+@(RK "$H$R`Once")+@(RK "$U$R")+@(RK "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"))
$if=@();try{Get-ChildItem "$H$W\Image File Execution Options" -ErrorAction SilentlyContinue|ForEach-Object{$d=RV $_.PSPath 'Debugger';if($d){$if+="$($_.PSChildName)->$d"}}}catch{}
A 'T1546.010' 'ifeo_dbg' $if
A 'T1546.009' 'appcert' (RK 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\AppCertDlls')
A 'T1546.010' 'appinit' (@(RV "$H$W\Windows" 'AppInit_DLLs')|Where-Object{$_})
A 'T1547.005' 'ssp' (@(RV "$H$L" 'SecurityPackages'))
A 'T1547.002' 'authpkg' (@(RV "$H$L" 'NotificationPackages'))
A 'T1547.004' 'winlogon' (@((RV "$H$W\Winlogon" 'Userinit')|Where-Object{$_ -and $_ -notmatch 'userinit'})+@((RV "$H$W\Winlogon" 'Shell')|Where-Object{$_ -and $_ -notmatch 'explorer'}))
A 'T1546.007' 'netsh' (RK 'HKLM:\SOFTWARE\Microsoft\Netsh')
$pm=@();try{Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors' -ErrorAction SilentlyContinue|ForEach-Object{$d=RV $_.PSPath 'Driver';if($d){$pm+="$($_.PSChildName)->$d"}}}catch{}
A 'T1547.010' 'portmon' $pm
A 'T1037.001' 'logonscript' (@(RV "$U\Environment" 'UserInitMprLogonScript')|Where-Object{$_})
$ac=@();try{Get-LocalUser -ErrorAction SilentlyContinue|Where-Object{$_.WhenCreated -gt (Get-Date).AddDays(-7)}|ForEach-Object{$ac+="$($_.Name) $($_.WhenCreated.ToString('o'))"}}catch{}
A 'T1136.001' 'new_acct' $ac
$fw=@();try{Get-NetFirewallProfile -ErrorAction SilentlyContinue|Where-Object{$_.Enabled -eq $false}|ForEach-Object{$fw+="$($_.Name):off"}}catch{}
A 'T1562.004' 'fw_off' $fw
[pscustomobject]@{skill='attackmap';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');track=$Track;checked=13;found=$o.Count;findings=@($o)}|ConvertTo-Json -Compress -Depth 5
