# Full configure + build (~16 min on a fast 8-job machine). Produces $SF_ROOT\port\bld\MyGameRecomp.exe
$ErrorActionPreference = 'Continue'; . "$PSScriptRoot\_toolchain.ps1"; $d = $env:SF_ROOT; $t = Get-Date
cmake -S "$d\port" -B "$d\port\bld" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl `
      -DPS3RECOMP_DIR="$d\ps3recomp" -DSPU_DIR="$d\port\spu" *> "$d\logs\03_configure.log"
"configure exit=$LASTEXITCODE" | Out-File "$d\logs\status.txt"
if ($LASTEXITCODE -eq 0) { cmake --build "$d\port\bld" -j 8 *> "$d\logs\04_build.log"; "build exit=$LASTEXITCODE minutes=$([int]((Get-Date)-$t).TotalMinutes)" | Out-File "$d\logs\status.txt" -Append }
