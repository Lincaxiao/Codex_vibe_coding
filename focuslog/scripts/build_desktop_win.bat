@echo off
setlocal
cd /d "%~dp0\..\.."

call focuslog\scripts\build_web.bat
if errorlevel 1 (
  echo [ERROR] Frontend build step failed.
  exit /b 1
)

echo [INFO] Building Windows desktop package...
pyinstaller --noconfirm --windowed --name FocusLog ^
  --paths . ^
  --distpath focuslog\dist ^
  --workpath focuslog\build ^
  --specpath focuslog ^
  focuslog\app_entry.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  exit /b 1
)

echo [OK] Desktop output: focuslog\dist\FocusLog
endlocal
