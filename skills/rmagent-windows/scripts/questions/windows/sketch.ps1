# Allowlisted: compact Administrator/SYSTEM smoke for the last window. Counts + short names.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
function Match-Track($ev) {
  foreach ($v in $ev.Properties.Value) { if ($Track -contains $v) { return $true } }
  return $false
}
$now = [DateTime]::UtcNow
$since = $now.AddHours(-$SinceHours)

# Failed Administrator/SYSTEM logons in window
$failed = 0
try {
  $failed = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=$since} |
              Where-Object { Match-Track $_ }).Count
} catch {}

# New local Administrators group members in last 24h (4732 = member added to local group)
# The member's friendly name is usually unresolved ("-"), so resolve the SID to a name.
function Get-EvField($e,$n){
  $x=[xml]$e.ToXml(); $m=New-Object System.Xml.XmlNamespaceManager($x.NameTable)
  $m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event')
  $n2=$x.SelectSingleNode("//e:Data[@Name='$n']",$m); if($n2){$n2.'#text'} else {$null}
}
$newAdmins = @()
try {
  $newAdmins = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4732; StartTime=$now.AddHours(-24)} |
                 Select-Object -First $Limit |
                 ForEach-Object {
                   $mn = Get-EvField $_ 'MemberName'
                   if ($mn -and $mn -ne '-') { $mn }
                   else {
                     $msid = Get-EvField $_ 'MemberSid'
                     if ($msid) {
                       try { ([System.Security.Principal.SecurityIdentifier]::new($msid)).Translate([System.Security.Principal.NTAccount]).Value }
                       catch { $msid }  # unresolved SID as-is (still a usable signal)
                     }
                   }
                 } | Select-Object -Unique)
} catch {}

# Services running as LocalSystem / Administrator (privileged service surface)
$svc = @()
try {
  $svc = @(Get-CimInstance Win32_Service -Filter "State='Running'" |
           Where-Object { $_.StartName -match 'LocalSystem|Administrator' } |
           Select-Object -First $Limit -ExpandProperty Name)
} catch {}

# Recently installed services (7045) and scheduled tasks created (4698) in window
$svcNew = 0; $taskNew = 0
try { $svcNew = @(Get-WinEvent -FilterHashtable @{LogName='System'; Id=7045; StartTime=$since}).Count } catch {}
try { $taskNew = @(Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4698; StartTime=$since}).Count } catch {}

[pscustomobject]@{
  skill            = 'sketch'
  host             = $env:COMPUTERNAME
  utc              = $now.ToString('o')
  window_hours     = $SinceHours
  track            = $Track
  admin_failed     = $failed
  new_local_admins = @($newAdmins)
  running_priv_svcs= @($svc)
  new_services     = $svcNew
  new_tasks        = $taskNew
} | ConvertTo-Json -Compress -Depth 3
