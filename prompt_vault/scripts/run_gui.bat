@echo off
setlocal
cd /d "%~dp0\..\.."
set "PV_CONDA_ENV=%PROMPT_VAULT_CONDA_ENV%"
if "%PV_CONDA_ENV%"=="" set "PV_CONDA_ENV=VibeCoding"

if /I "%PROMPT_VAULT_SKIP_WEB_BUILD%"=="1" (
  if not exist prompt_vault\frontend\dist\index.html (
    echo [INFO] Frontend dist not found, building web assets first...
    call prompt_vault\scripts\build_web.bat
    if errorlevel 1 exit /b 1
  )
) else (
  echo [INFO] Rebuilding frontend assets...
  call prompt_vault\scripts\build_web.bat
  if errorlevel 1 exit /b 1
)

where conda >nul 2>nul
if errorlevel 1 (
  echo [WARN] conda not found, using current python interpreter.
  python -m prompt_vault gui
  exit /b %errorlevel%
) else (
  call conda run -n %PV_CONDA_ENV% python -m prompt_vault gui
  exit /b %errorlevel%
)
endlocal
