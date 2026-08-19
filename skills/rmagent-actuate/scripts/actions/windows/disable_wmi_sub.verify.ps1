# disable_wmi_sub.verify — confirm the filter is gone. Engine injects $Target.
$still = Get-CimInstance -Namespace 'root\subscription' -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
         Where-Object { $_.Name -eq $Target }
if (-not $still) { 'VERIFIED' } else { 'NOT_VERIFIED' }
