@echo off
setlocal
cd /d "%~dp0\..\.."

set "PV_CONDA_ENV=%1"
if "%PV_CONDA_ENV%"=="" set "PV_CONDA_ENV=VibeCoding"

where conda >nul 2>nul
if errorlevel 1 (
  echo [ERROR] conda is not available in PATH.
  echo [HINT] Install Miniconda/Anaconda and retry.
  exit /b 1
)

echo [INFO] Installing GUI dependencies in conda env: %PV_CONDA_ENV%
call conda run -n %PV_CONDA_ENV% python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip/setuptools/wheel.
  exit /b 1
)

call conda run -n %PV_CONDA_ENV% python -m pip install --use-pep517 --no-warn-script-location -r prompt_vault\requirements-gui.txt
if errorlevel 1 (
  echo [ERROR] Failed to install GUI requirements.
  exit /b 1
)

echo [OK] GUI dependencies installed in %PV_CONDA_ENV%.
endlocal
