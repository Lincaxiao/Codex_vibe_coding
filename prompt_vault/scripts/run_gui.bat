@echo off
setlocal
cd /d "%~dp0\..\.."
python -m prompt_vault gui
endlocal
