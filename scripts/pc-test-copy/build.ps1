$ErrorActionPreference='Continue'
$d='%SF_LOCAL_PATH%'
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$env:PATH='%SF_LOCAL_PATH%'+$env:PATH
$env:PYTHONDONTWRITEBYTECODE='1'
$t=Get-Date
cmake -S "$d\port" -B "$d\port\bld" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl -DPS3RECOMP_DIR="$d\ps3recomp" -DPython3_EXECUTABLE="%SF_LOCAL_PATH%" *> "$d\logs\03_configure.log"
"configure exit=$LASTEXITCODE" | Out-File "$d\logs\status.txt"
if($LASTEXITCODE -eq 0){ cmake --build "$d\port\bld" -j 8 *> "$d\logs\04_build.log"; "build exit=$LASTEXITCODE minutes=$([int]((Get-Date)-$t).TotalMinutes)" | Out-File "$d\logs\status.txt" -Append }
"DONE" | Out-File "$d\logs\status.txt" -Append

