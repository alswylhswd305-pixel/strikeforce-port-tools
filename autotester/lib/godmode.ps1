# God-mode helper for the TEST COPY only (zero damage + no knockdown, once
# addresses are confirmed). Memory-poke, same style as TELEPORT_GO.
# Refuses a window titled "Saud plays". Do not run this against pid 45000
# or any session Saud is playing.
#
#   godmode.ps1 -mode status
#   godmode.ps1 -mode learn -Seconds 30          # watch near 0x8D3800
#   godmode.ps1 -mode learn -Seconds 30 -FullHeap
#   godmode.ps1 -mode on                         # freeze confirmed addrs only
#   godmode.ps1 -mode off
param(
    [ValidateSet('status','learn','on','off')][string]$mode = 'status',
    [int]$ProcId = 0,
    [int]$Seconds = 20,
    [int]$IntervalMs = 200,
    [switch]$FullHeap,
    [switch]$ForceMine,
    [string]$AddrFile = ''
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$cs = Join-Path $here 'SFAT_VM.cs'
if (-not ([System.Management.Automation.PSTypeName]'SFAT_VM').Type) { Add-Type -Path $cs }
if (-not $AddrFile) { $AddrFile = Join-Path $here '..\data\godmode_addrs.json' }

function Get-Target {
    if ($ProcId -gt 0) { return Get-Process -Id $ProcId -ErrorAction Stop }
    $p = Get-Process MyGameRecomp -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like '*TEST-SALEM*' }
    if (-not $p) { throw 'ما لقيت نافذة [TEST-SALEM]' }
    if (@($p).Count -gt 1 -and -not $ForceMine) { throw 'more than one [TEST-SALEM]; pass -ProcId' }
    return ($p | Select-Object -First 1)
}

$p = Get-Target
if (-not $ForceMine -and $p.MainWindowTitle -match 'Saud plays') {
    throw "refusing godmode on a 'Saud plays' window (pid $($p.Id))"
}
[SFAT_VM]::Open($p.Id)
$vb = [SFAT_VM]::FindBase()
if (-not $vb.Trim()) { throw 'no guest base' }
[SFAT_VM]::VB = [Convert]::ToInt64($vb.Trim().Split(' ')[0], 16)

$cfg = Get-Content $AddrFile -Raw | ConvertFrom-Json
$POS = 0x008D3800

function Show-Status {
    $x=[SFAT_VM]::RF($POS); $y=[SFAT_VM]::RF($POS+4); $z=[SFAT_VM]::RF($POS+8)
    "pid=$($p.Id) title='$($p.MainWindowTitle)' xyz=$x $y $z  status=$($cfg.status)"
    foreach ($a in @($cfg.confirmed_hp)) {
        $ea = [Convert]::ToInt64($a.ea.Replace('0x',''), 16)
        if ($a.kind -eq 'f32') { "  HP $($a.ea) = $([SFAT_VM]::RF($ea)) (f32)" }
        else { "  HP $($a.ea) = $([SFAT_VM]::R32($ea)) (u32)" }
    }
    if (-not $cfg.confirmed_hp) { '  confirmed_hp: (none — learn mode has not confirmed an address)' }
    foreach ($a in @($cfg.confirmed_knockdown)) {
        $ea = [Convert]::ToInt64($a.ea.Replace('0x',''), 16)
        "  knockdown $($a.ea) = $([SFAT_VM]::R32($ea))"
    }
}

function Get-Confirmed {
    $list = @()
    foreach ($a in @($cfg.confirmed_hp)) { $list += $a }
    foreach ($a in @($cfg.confirmed_knockdown)) { $list += $a }
    return $list
}

switch ($mode) {
    'status' { Show-Status }
    'off'    { 'godmode off (no background poke from this process unless -mode on is running)' }
    'on' {
        $list = Get-Confirmed
        if (-not $list -or $list.Count -eq 0) {
            throw "godmode on refused: no confirmed HP/knockdown addresses in $AddrFile. Run learn during a tester fight first."
        }
        $hold = @()
        foreach ($a in $list) {
            $ea = [Convert]::ToInt64(($a.ea -replace '0x',''), 16)
            $kind = [string]$a.kind
            $val = if ($kind -eq 'f32') { [SFAT_VM]::RF($ea) } else { [SFAT_VM]::R32($ea) }
            $hold += [pscustomobject]@{ ea=$ea; kind=$kind; val=$val; role=$a.role }
            "freeze $($a.ea) kind=$kind val=$val"
        }
        $t0 = Get-Date
        while ($true) {
            if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { 'proc gone'; break }
            foreach ($h in $hold) {
                if ($h.kind -eq 'f32') { [SFAT_VM]::WF($h.ea, [float]$h.val) }
                else { [SFAT_VM]::W32($h.ea, [uint32]$h.val) }
            }
            Start-Sleep -Milliseconds $IntervalMs
            if ($Seconds -gt 0 -and ((Get-Date)-$t0).TotalSeconds -ge $Seconds) { break }
        }
        'godmode poke loop ended'
    }
    'learn' {
        # Cheap default: 512 KiB around the proven player transform, 4-byte stride.
        # FullHeap repeats the old 128 MiB hunt and will hitch; only for a tester-owned window.
        $regions = @(@{ base = 0x008C0000; len = 0x00080000; name = 'near-xyz' })
        if ($FullHeap) { $regions += @{ base = 0x10000000; len = 0x08000000; name = 'heap' } }
        $outDir = Join-Path $here '..\reports'
        if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
        $out = Join-Path $outDir ("godmode_learn_{0:yyyyMMdd-HHmmss}.txt" -f (Get-Date))
        $lines = @("learn pid=$($p.Id) seconds=$Seconds fullheap=$FullHeap")
        foreach ($r in $regions) {
            $A = [SFAT_VM]::Snap($r.base, $r.len)
            $cand = New-Object 'System.Collections.Generic.List[int]'
            for ($o = 0; $o -le $r.len - 4; $o += 4) {
                $u = [SFAT_VM]::U($A, $o)
                $f = [SFAT_VM]::F($A, $o)
                if (($u -ge 20 -and $u -le 20000) -or ($f -ge 20 -and $f -le 20000 -and -not [float]::IsNaN($f))) {
                    $cand.Add($o) | Out-Null
                }
            }
            "region $($r.name) $($r.base.ToString('X8')) candidates=$($cand.Count)"
            $dec = New-Object 'int[]' $cand.Count
            $prev = $A
            $steps = [Math]::Max(1, [int]($Seconds * 1000 / $IntervalMs))
            for ($i = 0; $i -lt $steps; $i++) {
                Start-Sleep -Milliseconds $IntervalMs
                if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) { break }
                $B = [SFAT_VM]::Snap($r.base, $r.len)
                for ($k = 0; $k -lt $cand.Count; $k++) {
                    $o = $cand[$k]
                    $ua = [SFAT_VM]::U($prev, $o); $ub = [SFAT_VM]::U($B, $o)
                    if ($ua -eq $ub) { continue }
                    $fa = [SFAT_VM]::F($prev, $o); $fb = [SFAT_VM]::F($B, $o)
                    $isI = ($ua -ge 20 -and $ua -le 20000)
                    $dropped = if ($isI) { $ub -lt $ua } else { $fb -lt $fa -and $fb -ge 0 -and -not [float]::IsNaN($fb) }
                    if ($dropped) { $dec[$k]++ } else { $cand[$k] = -1 }
                }
                $prev = $B
            }
            $hits = @()
            for ($k = 0; $k -lt $cand.Count; $k++) {
                if ($cand[$k] -ge 0 -and $dec[$k] -gt 0) {
                    $ea = $r.base + $cand[$k]
                    $hits += "{0:X8} dec={1} now={2:X8}" -f $ea, $dec[$k], [SFAT_VM]::U($prev, $cand[$k])
                }
            }
            $lines += "--- $($r.name) hits=$($hits.Count) ---"
            $lines += $hits
            "  hits=$($hits.Count) (still unconfirmed until a human/tester marks them as player HP)"
        }
        $lines | Set-Content $out
        "wrote $out — addresses stay unconfirmed until copied into confirmed_hp after a verified hit."
    }
}
