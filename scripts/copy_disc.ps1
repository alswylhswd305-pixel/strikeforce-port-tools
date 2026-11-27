# Copy YOUR disc contents (folder with PS3_GAME, or a mounted ISO of your own disc) to $SF_ROOT\vfs\dev_bdvd.
# Optional -Iso: mounts an ISO you made from your own disc, read-only. Nothing here is ever committed.
param([string]$Source = $env:SF_DISC_SOURCE, [string]$Iso = "")
$d = $env:SF_ROOT; $img = $null
if ($Iso) { $img = Mount-DiskImage -ImagePath $Iso -Access ReadOnly -PassThru; $Source = (($img | Get-Volume).DriveLetter) + ':\' }
if (-not (Test-Path (Join-Path $Source 'PS3_GAME'))) { throw "No PS3_GAME folder in $Source" }
robocopy $Source "$d\vfs\dev_bdvd" /E /COPY:DT /R:1 /W:1 /NP /NFL /NDL /LOG:"$d\logs\10_robocopy.log"
"robocopy exit=$LASTEXITCODE"
if ($img) { Dismount-DiskImage -ImagePath $Iso | Out-Null }
