# snapshot - read-only baseline of the host's response-relevant state.
# Run BEFORE any action so the journal always has a "before" picture.
# Engine injects $Target (unused). Read-only; Stop only surfaces real errors.
$ErrorActionPreference = 'Stop'
try {
  $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{ name=$_.TaskName; state=$_.State; user=$_.Principal.UserId } })
  $services = @(Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{ name=$_.Name; state=$_.State; startmode=$_.StartMode; runas=$_.StartName } })
  $users = @(Get-LocalUser -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{ name=$_.Name; enabled=$_.Enabled } })
  $admins = @(Get-LocalGroupMember -Group Administrators -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
  $fw = @(Get-NetFirewallRule -DisplayName 'RMAgent-Block-*' -ErrorAction SilentlyContinue | ForEach-Object {
    [pscustomobject]@{ name=$_.DisplayName; enabled=$_.Enabled } })
  $wmi = @(Get-CimInstance -Namespace 'root\subscription' -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
           ForEach-Object { [pscustomobject]@{ name=$_.Name; query=$_.Query } })
  [pscustomobject]@{ action='snapshot'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o');
                     tasks=$tasks; services=$services; users=$users; admins=$admins; fw_rules=$fw; wmi_filters=$wmi } |
    ConvertTo-Json -Compress -Depth 4
} catch {
  [pscustomobject]@{ok=$false; action='snapshot'; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
