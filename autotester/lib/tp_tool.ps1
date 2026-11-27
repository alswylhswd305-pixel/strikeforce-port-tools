# Teleport wrapper for the test copy. Same guest address as the proven tool:
# X/Y/Z at 0x008D3800 (copies at 0x008D3860..0x16A1D9F0 follow). Tested
# 27-Nov 17:26 Asia/Kuwait: X=6499.8 -> 6799.8 held, minimap changed.
# Targets only a [TEST-SALEM] window. Refuses a window titled "Saud plays"
# unless -ForceMine is set by tester.ps1 on the PID it started.
param(
    [ValidateSet('save','go','read','goto','save-as')][string]$mode = 'read',
    [double]$X = [double]::NaN,
    [double]$Y = [double]::NaN,
    [double]$Z = [double]::NaN,
    [string]$Name = '',
    [int]$ProcId = 0,
    [switch]$ForceMine,
    [string]$Store = ''
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$cs = Join-Path $here 'SFAT_VM.cs'
if (-not ([System.Management.Automation.PSTypeName]'SFAT_VM').Type) { Add-Type -Path $cs -ErrorAction Stop }

$POS = 0x008D3800
if (-not $Store) { $Store = Join-Path $here '..\data\tp_saved.txt' }

function Get-Target {
    if ($ProcId -gt 0) { return Get-Process -Id $ProcId -ErrorAction Stop }
    $p = Get-Process MyGameRecomp -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like '*TEST-SALEM*' }
    if (-not $p) { throw 'ما لقيت نافذة [TEST-SALEM]' }
    if ($p.Count -gt 1 -and -not $ForceMine) { throw "more than one [TEST-SALEM] window; pass -ProcId" }
    return ($p | Select-Object -First 1)
}

$p = Get-Target
if (-not $ForceMine -and $p.MainWindowTitle -match 'Saud plays') {
    throw "refusing to teleport a 'Saud plays' window (pid $($p.Id))"
}
[SFAT_VM]::Open($p.Id)
$vb = [SFAT_VM]::FindBase()
if (-not $vb.Trim()) { throw 'no guest base (signature miss)' }
[SFAT_VM]::VB = [Convert]::ToInt64($vb.Trim().Split(' ')[0], 16)

function Read-Xyz { return @([SFAT_VM]::RF($POS), [SFAT_VM]::RF($POS+4), [SFAT_VM]::RF($POS+8)) }
function Write-Xyz([float]$x,[float]$y,[float]$z) {
    [SFAT_VM]::WF($POS, $x)
    [SFAT_VM]::WF($POS+4, $y)
    [SFAT_VM]::WF($POS+8, $z)
}

switch ($mode) {
    'read' {
        $v = Read-Xyz
        "pid=$($p.Id) base=$($vb.Trim()) X=$($v[0]) Y=$($v[1]) Z=$($v[2])"
    }
    'save' {
        $v = Read-Xyz
        $dir = Split-Path $Store -Parent
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        "$($v[0]) $($v[1]) $($v[2])" | Set-Content -LiteralPath $Store
        "saved $($v[0]) $($v[1]) $($v[2]) -> $Store"
    }
    'save-as' {
        if (-not $Name) { throw 'save-as needs -Name' }
        $v = Read-Xyz
        $json = Join-Path $here '..\data\checkpoints.json'
        $data = @{ checkpoints = @() }
        if (Test-Path $json) { $data = Get-Content $json -Raw | ConvertFrom-Json }
        $item = [pscustomobject]@{
            id = $Name
            xyz = @([double]$v[0],[double]$v[1],[double]$v[2])
            time = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
            pid = $p.Id
            evidence = 'TELEPORT_SAVE from autotester tp_tool'
            status = 'saved'
        }
        "saved-as $Name $($v[0]) $($v[1]) $($v[2])"
        # Caller should merge into checkpoints.json; also write a side file.
        $side = Join-Path $here "..\data\checkpoint_$Name.txt"
        "$($v[0]) $($v[1]) $($v[2])" | Set-Content $side
        $item | ConvertTo-Json -Compress
    }
    'go' {
        if (-not (Test-Path $Store)) { throw "no saved position at $Store" }
        $v = (Get-Content $Store).Split(' ') | ForEach-Object { [single]$_ }
        Write-Xyz $v[0] ($v[1] + 5) $v[2]   # Y+5, same as the proven TELEPORT_GO
        "go $($v[0]) $($v[1]+5) $($v[2])"
    }
    'goto' {
        if ([double]::IsNaN($X) -or [double]::IsNaN($Y) -or [double]::IsNaN($Z)) {
            throw 'goto needs -X -Y -Z'
        }
        Write-Xyz ([single]$X) ([single]($Y + 5)) ([single]$Z)
        "goto $X $($Y+5) $Z"
    }
}
