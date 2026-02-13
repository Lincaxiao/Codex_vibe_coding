@echo off
setlocal
cd /d "%~dp0\..\.."
call prompt_vault\scripts\build_desktop_win.bat
endlocal
