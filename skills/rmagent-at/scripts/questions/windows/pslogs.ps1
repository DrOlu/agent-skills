# pslogs — PowerShell script-block logging (Event 4104): the ACTUAL CODE being executed.
# Highest-fidelity signal in the skill — an -enc payload appears here as readable text.
# NOTE: UserId/Path are often EMPTY in 4104 (observed live); the user is in the event's
# Security descriptor, not a Data field. We return blocks unfiltered (capped) and let
# the operator read the code — every block is worth reading, unlike a process count.
# Log: Microsoft-Windows-PowerShell/Operational. Script-block logging was already ON
# on both WS1 and WS2 at probe time.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
$since=(Get-Date).AddHours(-$SinceHours)
$Max=[int]$Limit*20
$blocks=@()
try{
  $blocks=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-PowerShell/Operational';Id=4104;StartTime=$since} -MaxEvents $Max|
            Select-Object -First $Limit|
            ForEach-Object{
              $sb=(F $_ 'ScriptBlockText')
              [pscustomobject]@{
                t=$_.TimeCreated.ToString('o')
                path=(F $_ 'Path')
                msg= if($sb){$sb.Substring(0,[Math]::Min(500,$sb.Length))}else{''}
              }
            })
}catch{}
[pscustomobject]@{skill='pslogs';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;blocks=@($blocks)}|ConvertTo-Json -Compress -Depth 4
