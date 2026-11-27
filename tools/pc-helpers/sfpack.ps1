param([string[]]$runs,[string]$shot="shot_100s_client.png",[string]$zip="$env:TEMP\sfstep\pack.zip")
# Pack small jpgs of one shot from several run folders (+ DRAWLIST lines) for box-side viewing.
Add-Type -AssemblyName System.Drawing
$o="$env:TEMP\sfpack"; Remove-Item $o -Recurse -EA 0; New-Item -ItemType Directory $o | out-null
foreach($r in ($runs -split ',')){ $rd="$PSScriptRoot\runs\$r"; $f="$rd\$shot"; if(Test-Path $f){ $b=[Drawing.Image]::FromFile($f); $s=New-Object Drawing.Bitmap $b,960,([int](960*$b.Height/$b.Width)); $s.Save("$o\$r.jpg",[Drawing.Imaging.ImageFormat]::Jpeg); $b.Dispose(); $s.Dispose() }
  sls "$rd\stdout.log" -Pattern '^\[DRAWLIST\]' -EA 0 | % Line | Set-Content "$o\$r.drawlist.txt"
  if (-not (gc "$o\$r.drawlist.txt" -EA 0)) { Remove-Item "$o\$r.drawlist.txt" -EA 0 } }
Compress-Archive -Force "$o\*" $zip; "packed -> $zip"

