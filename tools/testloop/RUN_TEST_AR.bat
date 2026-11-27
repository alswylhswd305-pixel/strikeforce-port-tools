@echo off
rem Same as RUN_ALL_AR.bat (kept for the older name) - double-click: Arabic menu. With arguments: passes them to testloop.py
rem e.g.  RUN_ALL_AR.bat all --build 1780_shadowfix --route village
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PY=python"
if not exist "%PY%" set "PY=py"
cd /d "%~dp0"
"%PY%" "%~dp0testloop.py" %*
echo.
pause
