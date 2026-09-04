# canary — decoy-identity tripwire. ANY auth attempt against a canary is
# critical by definition: the identity exists only to be touched.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit; $CanaryList
#
# DESIGN: canaries are declared in the inventory as `canaries: [name,...]`.
# The engine passes them as $CanaryList. If none are declared we ALSO check
# the conventional decoy-name prefix/suffix list below so an estate that
# planted canaries without updating the inventory still gets coverage.
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
$DECOY_HINTS = @('canary','honey','decoy','tripwire','fakeadmin','svcbackup2')
$names = @()
try {
  $names = @($CanaryList) | Where-Object { $_ }
} catch {}
if (-not $names -or $names.Count -eq 0) {
  try {
    $names = @(Get-LocalUser -ErrorAction SilentlyContinue | ForEach-Object { $_.Name } |
              Where-Object { $n = $_.ToLower(); ($DECOY_HINTS | Where-Object { $n -like "*$_*" }).Count -gt 0 })
  } catch {}
}

$since = [DateTime]::UtcNow.AddHours(-$SinceHours)
$Max=[int]$Limit*20
$hits = @()
$armed = @()

foreach ($n in $names) {
  # 4624 SUCCESS against the canary = someone is IN (worst case)
  try {
    Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;StartTime=$since} -MaxEvents $Max -ErrorAction SilentlyContinue |
    Where-Object { (F $_ 'TargetUserName') -eq $n } | Select-Object -First $Limit | ForEach-Object {
      $hits += [pscustomobject]@{t=$_.TimeCreated.ToString('o');name=$n;id=4624;kind='success';
        src=(F $_ 'IpAddress');lid=(F $_ 'TargetLogonId');type=(F $_ 'LogonType');auth=(F $_ 'AuthenticationPackageName')}
    }
  } catch {}
  # 4625 FAILURE against the canary = someone is TRYING (still critical)
  try {
    Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625;StartTime=$since} -MaxEvents $Max -ErrorAction SilentlyContinue |
    Where-Object { (F $_ 'TargetUserName') -eq $n } | Select-Object -First $Limit | ForEach-Object {
      $hits += [pscustomobject]@{t=$_.TimeCreated.ToString('o');name=$n;id=4625;kind='failure';
        src=(F $_ 'IpAddress');lid='';type=(F $_ 'LogonType');auth=(F $_ 'AuthenticationPackageName')}
    }
  } catch {}
  # 4740 lockout of the canary = brute force against it
  try {
    Get-WinEvent -FilterHashtable @{LogName='Security';Id=4740;StartTime=$since} -MaxEvents $Max -ErrorAction SilentlyContinue |
    Where-Object { (F $_ 'TargetUserName') -eq $n } | Select-Object -First $Limit | ForEach-Object {
      $hits += [pscustomobject]@{t=$_.TimeCreated.ToString('o');name=$n;id=4740;kind='lockout';
        src=(F $_ 'IpAddress');lid='';type='';auth=''}
    }
  } catch {}
  $armed += $n
}

# distinct source IPs that touched any canary — the shortlist for actuate block_ip
$srcs = @($hits | Where-Object { $_.src -and $_.src -notmatch '^(127\.|0\.|::1|-)' } |
          ForEach-Object { $_.src } | Select-Object -Unique)

[pscustomobject]@{
  skill='canary'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o')
  since=$since.ToString('o')
  armed=@($armed)
  armed_count=@($armed).Count
  hit_count=@($hits).Count
  hits=@($hits | Select-Object -First $Limit)
  sources=@($srcs | Select-Object -First 20)
  tripped=(@($hits).Count -gt 0)
} | ConvertTo-Json -Compress -Depth 4