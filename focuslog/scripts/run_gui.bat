@echo off
setlocal
cd /d "%~dp0\..\.."
set "FOCUSLOG_CONDA_ENV=%FOCUSLOG_CONDA_ENV%"
if "%FOCUSLOG_CONDA_ENV%"=="" set "FOCUSLOG_CONDA_ENV=VibeCoding"

if /I "%FOCUSLOG_SKIP_WEB_BUILD%"=="1" (
  if not exist focuslog\frontend\dist\index.html (
    echo [INFO] Frontend dist not found, building web assets first...
    call focuslog\scripts\build_web.bat
    if errorlevel 1 exit /b 1
  )
) else (
  echo [INFO] Rebuilding frontend assets...
  call focuslog\scripts\build_web.bat
  if errorlevel 1 exit /b 1
)

where conda >nul 2>nul
if errorlevel 1 (
  echo [WARN] conda not found, using current python interpreter.
  python -m focuslog gui
  exit /b %errorlevel%
) else (
  call conda run -n %FOCUSLOG_CONDA_ENV% python -m focuslog gui
  exit /b %errorlevel%
)
endlocal
