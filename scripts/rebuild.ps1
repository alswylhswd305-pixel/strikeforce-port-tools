# Incremental rebuild after editing port\*.inc / stubs.cpp (seconds to a few minutes).
$ErrorActionPreference = 'Continue'; . "$PSScriptRoot\_toolchain.ps1"; $d = $env:SF_ROOT; $t = Get-Date
cmake --build "$d\port\bld" -j 8 *> "$d\logs\08_rebuild.log"
"rebuild exit=$LASTEXITCODE sec=$([int]((Get-Date)-$t).TotalSeconds)"
