@echo off
setlocal
cd /d "%~dp0\..\.."

call prompt_vault\scripts\build_web.bat
if errorlevel 1 (
  echo [ERROR] Frontend build step failed.
  exit /b 1
)

echo [INFO] Building Windows desktop package...
pyinstaller --noconfirm --windowed --name PromptVault ^
  --paths . ^
  --distpath prompt_vault\dist ^
  --workpath prompt_vault\build ^
  --specpath prompt_vault ^
  prompt_vault\app_entry.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  exit /b 1
)

echo [OK] Desktop output: prompt_vault\dist\PromptVault
endlocal
