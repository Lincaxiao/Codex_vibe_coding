@echo off
setlocal
cd /d "%~dp0\..\.."
pyinstaller --noconfirm --windowed --name FocusLog --paths . --distpath focuslog\\dist --workpath focuslog\\build --specpath focuslog focuslog\\app_entry.py
endlocal
