param([switch]$Baseline)
$ErrorActionPreference='Stop'
$t='%SF_LOCAL_PATH%'
$W="$t\sfauto\movie1786\build"; $S="$W\snap"
New-Item -ItemType Directory -Force $W,$S | Out-Null
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$llvm='%SF_LOCAL_PATH%'
$cl="$llvm\clang-cl.exe"; $lld="$llvm\lld-link.exe"
$B="$t\port\bld"
$ninja=Get-Content "$B\build.ninja"
$linkLine=($ninja | Select-String -Pattern '^build MyGameRecomp.exe:').Line
$objs=($linkLine -replace '^build MyGameRecomp.exe: CXX_EXECUTABLE_LINKER__MyGameRecomp_Release ','') -split ' ' | ?{ $_ -like '*.obj' }
# snapshot every object + the runtime lib once (port\bld is shared with other workers)
if(-not (Test-Path "$S\done.txt")){
  foreach($o in $objs){ $dst=Join-Path $S $o; New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null; Copy-Item (Join-Path $B $o) $dst }
  Copy-Item "$B\ps3recomp_sdk\ps3recomp_runtime.lib" "$S\ps3recomp_runtime.lib"
  "snap $(Get-Date)" | Out-File "$S\done.txt"
}
$flags='/DWIN32 /D_WINDOWS /EHsc /O2 /Ob2 /DNDEBUG -std:c++20 -MD -Wno-unused-parameter -fno-strict-aliasing -fwrapv -msse4.1 -w'
$inc=@("$t\port\recompiled","$t\ps3recomp\include","$t\ps3recomp\runtime\ppu","$t\ps3recomp\runtime\spu","$t\ps3recomp\runtime\memory","$t\ps3recomp\runtime\syscalls","$t\ps3recomp\runtime\platform","$t\ps3recomp\libs\video","$t\port","$W","$t\ps3recomp\third_party\at3_standalone") | % { "-I$_" }
function CC($src,$obj){ & $cl /nologo -TP $flags.Split(' ') $inc /Fo$obj -c -- $src; if($LASTEXITCODE){ throw "compile failed: $src" } }
# stubs.cpp with the movie player registered after the other overrides
$st=Get-Content "$t\port\stubs.cpp" -Raw
if(-not $Baseline){
  $st=$st.Replace('#include "strikeforce_sail.inc"', "#include `"strikeforce_sail.inc`"`r`n#include `"strikeforce_movie.inc`"")
  $st=$st.Replace('sf_register_sail_overrides();','sf_register_sail_overrides(); sf_register_movie_overrides();')
  if($st -notmatch 'sf_register_movie_overrides\(\);'){ throw 'register hook not inserted' }
}
$tag= if($Baseline){'base'}else{'movie'}
Set-Content "$W\stubs_$tag.cpp" $st -NoNewline
Copy-Item "$t\sfauto\movie1786\strikeforce_movie.inc" "$W\strikeforce_movie.inc" -Force
CC "$W\stubs_$tag.cpp" "$W\stubs_$tag.obj"
foreach($n in 'ppu_hle','ppu_loader'){ if(-not (Test-Path "$W\$n.obj")){ CC "$t\ps3recomp\runtime\ppu\$n.cpp" "$W\$n.obj" } }
$list=@()
foreach($o in $objs){
  if($o -like '*\stubs.cpp.obj'){ $list+="$W\stubs_$tag.obj" }
  elseif($o -like '*\ppu_hle.cpp.obj'){ $list+="$W\ppu_hle.obj" }
  elseif($o -like '*\ppu_loader.cpp.obj'){ $list+="$W\ppu_loader.obj" }
  else { $list+=(Join-Path $S $o) }
}
$list+="$S\ps3recomp_runtime.lib"
$list+='dbghelp.lib user32.lib gdi32.lib winmm.lib ws2_32.lib ole32.lib bcrypt.lib kernel32.lib winspool.lib shell32.lib oleaut32.lib uuid.lib comdlg32.lib advapi32.lib mfplat.lib mfuuid.lib'.Split(' ')
$list | % { "`"$_`"" } | Set-Content "$W\link_$tag.rsp"
& $lld /nologo "@$W\link_$tag.rsp" /out:"$W\MyGameRecomp_$tag.exe" /machine:x64 /INCREMENTAL:NO /subsystem:console
if($LASTEXITCODE){ throw 'link failed' }
Get-Item "$W\MyGameRecomp_$tag.exe" | select Name,Length,LastWriteTime | Format-Table -AutoSize | Out-String
