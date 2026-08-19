# disable_wmi_sub — delete a WMI event subscription, recording the query first
# (the query goes to the journal via result_detail so it can be recreated).
# Engine injects $Target (subscription name — the __EventFilter Name, or the
# CommandLineEventConsumer Name; we search both namespaces).
$found = $null; $query = $null; $class = $null
foreach ($ns in @('root\subscription')) {
  $f = Get-CimInstance -Namespace $ns -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -eq $Target }
  if ($f) { $found = $f; $query = $f.Query; $class = '__EventFilter'; break }
}
if (-not $found) {
  [pscustomobject]@{ action='disable_wmi_sub'; target=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  # remove the filter and anything bound to it
  Get-CimInstance -Namespace 'root\subscription' -ClassName '__FilterToConsumerBinding' -ErrorAction SilentlyContinue |
    Where-Object { $_.Filter -match $Target } | Remove-CimInstance -ErrorAction SilentlyContinue
  Remove-CimInstance -InputObject $found -ErrorAction SilentlyContinue
  $still = Get-CimInstance -Namespace 'root\subscription' -ClassName '__EventFilter' -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -eq $Target }
  [pscustomobject]@{ action='disable_wmi_sub'; target=$Target; status= if($still){'failed'}else{'deleted' };
                     query=$query; wmi_class=$class } | ConvertTo-Json -Compress -Depth 3
}
