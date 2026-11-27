param([int]$proc,[string]$press="",[int]$n=40,[double]$wait=1.5,[string]$name="s",[string]$padfile)
# Screen-guided input: write one press to the PAD_FILE, wait, capture the client area as a small jpg.
if ($press) { Set-Content -Path $padfile -Value "$press $n" -NoNewline }
Start-Sleep -Milliseconds ([int]($wait*1000))
$o="$env:TEMP\sfstep"; New-Item -ItemType Directory $o -Force | out-null
Remove-Item "$o\$name.png","$o\$($name)_client.png","$o\$name.jpg" -ea SilentlyContinue; $png="$o\$name.png"; $r = & powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\shot.ps1" -ProcId $proc -Out $png
Add-Type -AssemblyName System.Drawing
$cp=$png -replace '\.png$','_client.png'; $src= if (Test-Path $cp) { $cp } else { $png }
$b=[Drawing.Image]::FromFile($src); $s=New-Object Drawing.Bitmap $b,960,([int](960*$b.Height/$b.Width)); $s.Save("$o\$name.jpg",[Drawing.Imaging.ImageFormat]::Jpeg); $b.Dispose(); $s.Dispose()
"$r -> $o\$name.jpg"
