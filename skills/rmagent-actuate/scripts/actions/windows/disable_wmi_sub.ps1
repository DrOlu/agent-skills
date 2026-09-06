# disable_wmi_sub - delete a WMI event subscription, recording the FULL
# triple first (Rev 17, M3): the __EventFilter (name + query), the consumers
# bound to it, and the __FilterToConsumerBinding count. The old payload
# captured only the filter query.
# Engine injects $Target (the __EventFilter Name).
$ErrorActionPreference = 'Stop'
try {
  $ns = 'root\subscription'
  $f = Get-CimInstance -Namespace $ns -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -eq $Target } | Select-Object -First 1
  if (-not $f) {
    [pscustomobject]@{ action='disable_wmi_sub'; target=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    # capture the full triple BEFORE deleting anything
    $bindings = @(Get-CimInstance -Namespace $ns -ClassName '__FilterToConsumerBinding' -ErrorAction SilentlyContinue |
      Where-Object { ($_.Filter -replace '^.*\\\\','') -match [regex]::Escape($Target) })
    $consumers = @()
    foreach ($b in $bindings) {
      $cRef = $b.Consumer
      if ($cRef) {
        $consumers += [pscustomobject]@{ ref=$cRef }
      }
    }
    foreach ($b in $bindings) { Remove-CimInstance -InputObject $b -ErrorAction SilentlyContinue }
    Remove-CimInstance -InputObject $f -ErrorAction Stop
    $still = Get-CimInstance -Namespace $ns -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -eq $Target }
    [pscustomobject]@{ action='disable_wmi_sub'; target=$Target;
                       status= if($still){'failed'}else{'deleted'};
                       filter_query=$f.Query;
                       bindings_removed=@($bindings).Count;
                       consumers=$consumers } | ConvertTo-Json -Compress -Depth 4
  }
} catch {
  [pscustomobject]@{ok=$false; action='disable_wmi_sub'; target=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
