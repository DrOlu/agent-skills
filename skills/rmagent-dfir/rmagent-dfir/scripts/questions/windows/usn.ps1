# usn — USN journal tail on C:. Recent file activity the event log never
# shows (renames, creations, truncations). Keeps the interesting reasons.
$T=120
$rows=@();try{$raw=(fsutil usn readjournal C: csv 2>$null)|Select -Last 4000}catch{}
foreach($l in $raw){
  if($l -match '^(.*?), 0x([0-9a-fA-F]+)'){ $fn=$Matches[1].Trim(); $rs=$Matches[2]
    if($fn -match '(?i)(temp|appdata|public|downloads|\.exe|\.ps1|\.dll|\.scr|\.vbs|\.js)'){
      $reasons=@();if(($rs -band 0x80000000) -ne 0){$reasons+='new'};if(($rs -band 0x1) -ne 0){$reasons+='data-overwrite'};if(($rs -band 0x2) -ne 0){$reasons+='data-extend'};if(($rs -band 0x10000000) -ne 0){$reasons+='close'};if(($rs -band 0x20000) -ne 0){$reasons+='rename-new'};if(($rs -band 0x1000) -ne 0){$reasons+='delete'}
      if($reasons.Count -gt 0 -and $rows.Count -lt $Limit){if($fn.Length -gt $T){$fn=$fn.Substring(0,$T)+'…'};$rows+=[pscustomobject]@{file=$fn;reason=($reasons -join '+')}}
    }
  }
}
[pscustomobject]@{skill='usn';host=$env:COMPUTERNAME;utc=(Get-Date).ToUniversalTime().ToString('o');rows=$rows.Count;entries=$rows;note='USN tail is a sample, not the whole journal — holes are honest'}|ConvertTo-Json -Compress -Depth 4
