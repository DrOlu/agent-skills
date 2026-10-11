# irhash — hash a semicolon-separated list of files. Read-only.
param([string]$List)
$ErrorActionPreference='SilentlyContinue'
$out=@()
foreach($p in ($List -split ';')){
  if(-not $p.Trim()){continue}
  $f=Get-Item $p.Trim() -Force -ErrorAction SilentlyContinue
  if($f -and -not $f.PSIsContainer){
    $h=Get-FileHash $f.FullName -Algorithm SHA256 -ErrorAction SilentlyContinue
    $out+=[pscustomobject]@{path=$f.FullName;size=$f.Length;mtime=$f.LastWriteTimeUtc.ToString('o');sha256=$h.Hash.ToLower()}
  }else{$out+=[pscustomobject]@{path=$p.Trim();error='not found'}}
}
[pscustomobject]@{ok=$true;files=$out}|ConvertTo-Json -Compress -Depth 4
