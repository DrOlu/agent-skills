# ircollect — parameterized, READ-ONLY file acquisition. dfir.py validates the
# path before this ever runs; this payload validates again (defense in depth).
# One chunk per call: base64 body + per-chunk and full-file SHA256.
param([string]$Path,[int]$Chunk,[int]$ChunkSize=24576)
$ErrorActionPreference='Stop'
$p=[IO.Path]::GetFullPath($Path)
if($p -notmatch '^[A-Za-z]:\\'){Write-Output ('{"ok":false,"error":"path must be drive-absolute"}');exit 1}
if(-not (Test-Path $p -PathType Leaf)){Write-Output ('{"ok":false,"error":"not a file: '+$p.Replace('"','')+'"}');exit 1}
$fi=Get-Item $p -Force
$fs=[IO.File]::OpenRead($p)
try{
  $total=$fs.Length
  $chunks=[int][Math]::Ceiling($total/[double]$ChunkSize)
  if($chunks -eq 0){$chunks=1}
  if($Chunk -ge $chunks){Write-Output ('{"ok":false,"error":"chunk out of range"}');exit 1}
  $null=$fs.Seek($Chunk*[long]$ChunkSize,'Begin')
  $len=[int][Math]::Min($ChunkSize,$total-$Chunk*$ChunkSize)
  $buf=New-Object byte[] $len
  $null=$fs.Read($buf,0,$len)
  $sha=[System.Security.Cryptography.SHA256]::Create()
  $csha=[BitConverter]::ToString($sha.ComputeHash($buf)).Replace('-','').ToLower()
  $fs.Seek(0,'Begin')|Out-Null
  $fsha=[BitConverter]::ToString($sha.ComputeHash($fs)).Replace('-','').ToLower()
  [pscustomobject]@{ok=$true;path=$p;size=$total;chunks=$chunks;index=$Chunk;chunk_bytes=$len;sha256_chunk=$csha;sha256_file=$fsha;mtime=$fi.LastWriteTimeUtc.ToString('o');data=[Convert]::ToBase64String($buf)}|ConvertTo-Json -Compress
}finally{$fs.Close()}
