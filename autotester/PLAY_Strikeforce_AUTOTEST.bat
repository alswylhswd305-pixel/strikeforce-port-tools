@echo off
setlocal
rem TEST COPY only. Does not change PLAY_Strikeforce.bat.
rem Own state (sfauto\state_autotest), own pad (sfauto\autotester\pad.txt).
title [TEST-SALEM] Strikeforce AUTOTEST
set "SF=%~dp0..\.."
if not exist "%SF%\port\CMakeLists.txt" set "SF=%SF_LOCAL_PATH%"
if "%SF:~-1%"=="\" set "SF=%SF:~0,-1%"
set "PS3_VFS_ROOT=%SF%\vfs\dev_bdvd"
set "PS3_HDD0_ROOT=%SF%\sfauto\state_autotest\hdd0"
set "PS3_HDD1_ROOT=%SF%\sfauto\state_autotest\hdd1"
set "PS3_GAMEDATA_ROOT=%SF%\sfauto\state_autotest\gamedata"
set "PS3_DEV_FLASH=%SF_LOCAL_PATH%"
set "PS3_TITLE=[TEST-SALEM] ps3recomp AUTOTEST"
set "PS3_HLE_TOP=0"
set "SPU_INTERP_UNLIFTED=1"
set "SPU_INTERP_MISS=1"
set "OSK_AUTO_TEXT=Saud"
set "SF_PADMAP=%SF%\Strikeforce_buttons.ini"
set "PAD_FILE=%SF%\sfauto\autotester\pad.txt"
set "PAD_NO_XINPUT=1"
set "SF_MOVIE_LOG=1"
set "SF_HLE_LRLOG=1"
set "SF_GODMODE=%SF_GODMODE%"
set "SF_GODMODE_ADDRS=%SF%\sfauto\autotester\data\godmode_addrs.txt"
set "ELF=%SF_LOCAL_PATH%"
if not exist "%SF%\play_cwd" mkdir "%SF%\play_cwd"
if not exist "%SF%\play_logs" mkdir "%SF%\play_logs"
if not exist "%SF%\sfauto\state_autotest" mkdir "%SF%\sfauto\state_autotest"
for /f %%t in ('powershell -NoProfile -Command "Get-Date -f yyyyMMdd-HHmmss"') do set "TS=%%t"
cd /d "%SF%\play_cwd"
rem Prefer a dedicated 1786_autotest exe if present; otherwise movie v5 (movies work, HLE coverage may be missing).
set "EXE=%SF%\sfauto\exe_copies\1786_autotest\MyGameRecomp.exe"
if not exist "%EXE%" set "EXE=%SF%\sfauto\exe_copies\1786_movie_v5\MyGameRecomp.exe"
"%EXE%" "%ELF%" 1>"%SF%\play_logs\autotest_%TS%_stdout.log" 2>"%SF%\play_logs\autotest_%TS%_stderr.log"
echo Game exited with code %ERRORLEVEL%.
echo %TS%> "%SF%\sfauto\autotester\last_run_ts.txt"
endlocal
