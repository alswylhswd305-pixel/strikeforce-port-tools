$ErrorActionPreference='Stop'
# [TEST-SALEM] spursfix1791: 1791 SPURS taskset teardown fix (test copy) on bundle1787 = 1786_movie_v5 + [sf-lc] lifecycle + LFQ/SPU queue watch + SF_ATRAC_LOG fields + RSX_CENSUS. Shared source tree untouched.
$t='<TEST_COPY>'; $R="$t\sfauto\spursfix1791"; $Src="$R\src"; $W="$R\build"; $S="$t\sfauto\movie1786\build\snap"; $MB="$t\sfauto\movie1786\build"
New-Item -ItemType Directory -Force $W | Out-Null
$tree=@("$t\ps3recomp\runtime\spu\spu_channels.c","$t\ps3recomp\libs\spurs\cellSpurs.c","$t\ps3recomp\runtime\spu\spu_workload.c","$t\ps3recomp\libs\codec\cellAtrac.c","$t\ps3recomp\libs\video\rsx_commands.c","$t\port\strikeforce_lfqueue.inc","$t\port\stubs.cpp","$MB\rsx_d3d12_backend_v5.c","$MB\stubs_movie.cpp","$MB\strikeforce_movie.inc")
$tree | % { "{0} {1}" -f (Get-FileHash $_ -A MD5).Hash,$_ } | Set-Content "$R\tree_md5_before.txt"
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul && set' | % { if($_ -match '^([^=]+)=(.*)$'){ Set-Item "env:$($matches[1])" $matches[2] } }
$llvm='<LLVM_BIN>'; $cl="$llvm\clang-cl.exe"; $lld="$llvm\lld-link.exe"; $B="$t\port\bld"
$n2=[IO.File]::ReadAllLines("$B\build.ninja")
function NF($rel){ $ix=[Array]::FindIndex($n2,[Predicate[string]]{ param($x) $x -like "build ps3recomp_sdk\CMakeFiles\ps3recomp_runtime.dir\$rel.obj:*" }); if($ix -lt 0){ throw "no ninja rule $rel" }
  $f=(($n2[($ix+1)..($ix+8)] | ? { $_ -match '^\s+FLAGS = ' }) -replace '^\s+FLAGS = ','').Split(' ') | ? { $_ }
  $i=(($n2[($ix+1)..($ix+8)] | ? { $_ -match '^\s+INCLUDES = ' }) -replace '^\s+INCLUDES = ','').Split(' ') | ? { $_ }
  ,@($f,$i) }
function CCR($rel,$file){ $fi=NF $rel; $obj="$W\$([IO.Path]::GetFileNameWithoutExtension($file)).obj"; $o=& $cl /nologo -TC $fi[0] "-I$Src" $fi[1] -w "/Fo$obj" -c -- "$Src\$file" 2>&1; $o | % { "$_" } | ? { $_ -match 'error' } | Select -First 20; if($LASTEXITCODE){ throw "compile failed: $file" }; "compiled $file"; $obj }
$objs=(($n2 | Select-String -Pattern '^build MyGameRecomp.exe:').Line -replace '^build MyGameRecomp.exe: CXX_EXECUTABLE_LINKER__MyGameRecomp_Release ','') -split ' ' | ?{ $_ -like '*.obj' }
$extra=@()
$extra+=(CCR 'runtime\spu\spu_channels.c' 'spu_channels.c')[-1]
$extra+=(CCR 'libs\spurs\cellSpurs.c' 'cellSpurs.c')[-1]
$extra+=(CCR 'runtime\spu\spu_workload.c' 'spu_workload.c')[-1]
$extra+=(CCR 'libs\codec\cellAtrac.c' 'cellAtrac.c')[-1]
$extra+=(CCR 'libs\video\rsx_commands.c' 'rsx_commands.c')[-1]
$extra+=(CCR 'libs\video\rsx_d3d12_backend.c' 'rsx_d3d12_backend.c')[-1]
$xflags='/DWIN32 /D_WINDOWS /EHsc /O2 /Ob2 /DNDEBUG -std:c++20 -MD -Wno-unused-parameter -fno-strict-aliasing -fwrapv -msse4.1 -w'.Split(' ')
$xinc=@("$Src","$t\port\recompiled","$t\ps3recomp\include","$t\ps3recomp\runtime\ppu","$t\ps3recomp\runtime\spu","$t\ps3recomp\runtime\memory","$t\ps3recomp\runtime\syscalls","$t\ps3recomp\runtime\platform","$t\ps3recomp\libs\video","$t\port","$t\ps3recomp\third_party\at3_standalone") | % { "-I$_" }
$o=& $cl /nologo -TP $xflags $xinc "/Fo$W\stubs_bundle.obj" -c -- "$Src\stubs_movie.cpp" 2>&1; $o | % { "$_" } | ? { $_ -match 'error' } | Select -First 20; if($LASTEXITCODE){ throw 'compile failed: stubs_movie.cpp' }; 'compiled stubs_movie.cpp'
# ppu_hle / ppu_loader: the 1786 voicediag objects from the snapshot (log-only diag: SF_HLE_LRLOG), not the plain-tree ones v5 used
$list=@(); foreach($o in $objs){ if($o -eq 'CMakeFiles\MyGameRecomp.dir\stubs.cpp.obj'){ $list+="$W\stubs_bundle.obj" } else { $list+=(Join-Path $S $o) } }
$list+=$extra; $list+="$S\ps3recomp_runtime.lib"
$list+='dbghelp.lib user32.lib gdi32.lib winmm.lib ws2_32.lib ole32.lib bcrypt.lib kernel32.lib winspool.lib shell32.lib oleaut32.lib uuid.lib comdlg32.lib advapi32.lib mfplat.lib mfuuid.lib'.Split(' ')
$list | % { "`"$_`"" } | Set-Content "$W\link.rsp"
$lo=& $lld /nologo "@$W\link.rsp" /out:"$W\MyGameRecomp_spursfix1791.exe" /machine:x64 /INCREMENTAL:NO /subsystem:console 2>&1; $lo | % { "$_" } | Select -First 30
if($LASTEXITCODE){ throw 'link failed' }
$tree | % { "{0} {1}" -f (Get-FileHash $_ -A MD5).Hash,$_ } | Set-Content "$R\tree_md5_after.txt"
if((Get-Content "$R\tree_md5_before.txt" -Raw) -ne (Get-Content "$R\tree_md5_after.txt" -Raw)){ 'WARNING: source tree changed during build' } else { 'source tree unchanged (md5 before == after)' }
$e=Get-Item "$W\MyGameRecomp_spursfix1791.exe"; "$($e.Name) $($e.Length) $((Get-FileHash $e.FullName -A MD5).Hash)"

