# Relink a build with /MAP into port\bld\map_<tag>\ (does not touch MyGameRecomp.exe).
param([string]$tag)
$d='%SF_LOCAL_PATH%'
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$env:PATH='%SF_LOCAL_PATH%'+$env:PATH
cd "$d\port\bld"
ninja ps3recomp_sdk\ps3recomp_runtime.lib CMakeFiles\MyGameRecomp.dir\stubs.cpp.obj 2>&1 | select -Last 2
$cmd = (ninja -t commands MyGameRecomp.exe | select -Last 1)
New-Item -ItemType Directory "map_$tag" -Force | out-null
$cmd = $cmd -replace '/out:MyGameRecomp.exe', "/out:map_$tag\MyGameRecomp.exe /MAP:map_$tag\MyGameRecomp.map" -replace '/implib:\S+', "/implib:map_$tag\x.lib" -replace '/pdb:\S+', "/pdb:map_$tag\MyGameRecomp.pdb"
$cmd.Substring(0,[Math]::Min(400,$cmd.Length))
python $env:TEMP\mkrsp.py; $rsp="$env:TEMP\maplink_cmd.cmd"; Set-Content $rsp $cmd -Encoding ascii; cmd /c $rsp 2>&1 | select -Last 5
gci "map_$tag" | select Name,Length


