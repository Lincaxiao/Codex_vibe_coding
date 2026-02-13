@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist focuslog\frontend\package.json (
  echo [ERROR] Missing focuslog/frontend/package.json
  exit /b 1
)

if /I "%FOCUSLOG_NPM_INSTALL%"=="1" (
  goto install_deps
)

if not exist focuslog\frontend\node_modules (
  goto install_deps
)

echo [INFO] Reusing existing frontend node_modules (set FOCUSLOG_NPM_INSTALL=1 to force reinstall).
goto build_frontend

:install_deps
echo [INFO] Installing frontend dependencies...
call npm --prefix focuslog/frontend install --no-audit --no-fund --loglevel=error
if errorlevel 1 (
  echo [ERROR] npm install failed.
  exit /b 1
)

:build_frontend
echo [INFO] Building frontend...
call npm --prefix focuslog/frontend run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)

echo [OK] Frontend build output: focuslog/frontend/dist
endlocal
