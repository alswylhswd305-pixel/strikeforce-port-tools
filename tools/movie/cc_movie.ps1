$t='%SF_LOCAL_PATH%'; $W="$t\sfauto\movie1786\build"
Copy-Item "$t\sfauto\movie1786\strikeforce_movie.inc" "$W\strikeforce_movie.inc" -Force
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$cl='%SF_LOCAL_PATH%'
$flags='/DWIN32 /D_WINDOWS /EHsc /O2 /Ob2 /DNDEBUG -std:c++20 -MD -Wno-unused-parameter -fno-strict-aliasing -fwrapv -msse4.1 -w'
$inc=@("$t\port\recompiled","$t\ps3recomp\include","$t\ps3recomp\runtime\ppu","$t\ps3recomp\runtime\spu","$t\ps3recomp\runtime\memory","$t\ps3recomp\runtime\syscalls","$t\ps3recomp\runtime\platform","$t\ps3recomp\libs\video","$t\port",$W,"$t\ps3recomp\third_party\at3_standalone") | % { "-I$_" }
$out = & $cl /nologo -TP $flags.Split(' ') $inc "/Fo$W\stubs_movie.obj" -c -- "$W\stubs_movie.cpp" 2>&1
$out | % { "$_" } | ? { $_ -match 'error' } | select -First 30
"exit=$LASTEXITCODE"
