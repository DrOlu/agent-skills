# procrun — Prefetch program-run evidence: name + last-run time; LOLBins
# flagged. Prefetch only exists when enabled (default on workstations).
$L=@('certutil','bitsadmin','mshta','rundll32','regsvr32','wscript','cscript','powershell','cmd','installutil','msbuild','curl','schtasks','wmic','vssadmin','bcdedit','diskshadow','secedit')
$P=@();$tot=0;try{foreach($f in (Get-ChildItem 'C:\Windows\Prefetch\*.pf' -File -ErrorAction Stop|Sort-Object LastWriteTimeUtc -Descending)){$tot++;if($P.Count -lt $Limit){$bn=$f.BaseName.ToLower();$int=@($L|Where-Object{$bn -eq $_ -or $bn.StartsWith($_+'-')}).Count -gt 0;$P+=[pscustomobject]@{name=$f.BaseName;lastrun=($f.LastWriteTimeUtc.ToString('o'));lolbin=$int}}}}catch{}
[pscustomobject]@{skill='procrun';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');prefetch_total=$tot;recent=$P;note='empty = disabled or cleaned (itself a signal on a workstation)'}|ConvertTo-Json -Compress -Depth 4
