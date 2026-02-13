@echo off
setlocal
cd /d "%~dp0\..\.."
call focuslog\scripts\build_desktop_win.bat
endlocal
