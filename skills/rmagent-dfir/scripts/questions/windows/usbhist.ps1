# usbhist — USB device history + mount evidence. Registry-only, read-only.
$T=140
$dev=@();try{foreach($p in Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Enum\USBSTOR' -ErrorAction Stop){foreach($c in Get-ChildItem $p.PSPath){$nm=Split-Path -Leaf $p.PSChildName;$sn=Split-Path -Leaf $c.PSChildName;if($dev.Count -lt $Limit){$dev+=[pscustomobject]@{device=($(if($nm.Length -gt $T){$nm.Substring(0,$T)+'…'}else{$nm}));serial=$sn}}}}}catch{}
$md=@();try{foreach($pr in (Get-ItemProperty 'HKLM:\SYSTEM\MountedDevices' -ErrorAction Stop).PSObject.Properties){if($pr.Name -like '\DosDevices*'){if($md.Count -lt $Limit){$md+=[pscustomobject]@{dos=$pr.Name;data=($(if(($pr.Value|Out-String).Length -gt $T){($pr.Value|Out-String).Substring(0,$T)+'…'}else{($pr.Value|Out-String).Trim()}))}}}}}catch{}
[pscustomobject]@{skill='usbhist';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');usb_devices=$dev;mounted_devices=$md}|ConvertTo-Json -Compress -Depth 5
