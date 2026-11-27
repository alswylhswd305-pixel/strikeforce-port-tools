$ErrorActionPreference='Continue'
$d='%SF_LOCAL_PATH%'
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$env:PATH='%SF_LOCAL_PATH%'+$env:PATH
$env:PYTHONDONTWRITEBYTECODE='1'
$t=Get-Date
$t=Get-Date
cmake --build "$d\port\bld" -j 8 *> "$d\logs\08_rebuild.log"
"rebuild exit=$LASTEXITCODE sec=$([int]((Get-Date)-$t).TotalSeconds)" | Out-File "$d\logs\status8.txt"
