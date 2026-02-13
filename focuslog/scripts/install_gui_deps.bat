@echo off
setlocal
cd /d "%~dp0\..\.."

set "FOCUSLOG_CONDA_ENV=%1"
if "%FOCUSLOG_CONDA_ENV%"=="" set "FOCUSLOG_CONDA_ENV=VibeCoding"

where conda >nul 2>nul
if errorlevel 1 (
  echo [ERROR] conda is not available in PATH.
  echo [HINT] Install Miniconda/Anaconda and retry.
  exit /b 1
)

echo [INFO] Installing GUI dependencies in conda env: %FOCUSLOG_CONDA_ENV%
call conda run -n %FOCUSLOG_CONDA_ENV% python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip/setuptools/wheel.
  exit /b 1
)

call conda run -n %FOCUSLOG_CONDA_ENV% python -m pip install --use-pep517 --no-warn-script-location -r focuslog\requirements-gui.txt
if errorlevel 1 (
  echo [ERROR] Failed to install GUI requirements.
  exit /b 1
)

echo [OK] GUI dependencies installed in %FOCUSLOG_CONDA_ENV%.
endlocal
