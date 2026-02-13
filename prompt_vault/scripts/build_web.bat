@echo off
setlocal
cd /d "%~dp0\..\.."

if not exist prompt_vault\frontend\package.json (
  echo [ERROR] Missing prompt_vault/frontend/package.json
  exit /b 1
)

if /I "%PROMPT_VAULT_NPM_INSTALL%"=="1" (
  goto install_deps
)

if not exist prompt_vault\frontend\node_modules (
  goto install_deps
)

echo [INFO] Reusing existing frontend node_modules (set PROMPT_VAULT_NPM_INSTALL=1 to force reinstall).
goto build_frontend

:install_deps
echo [INFO] Installing frontend dependencies...
call npm --prefix prompt_vault/frontend install --no-audit --no-fund --loglevel=error
if errorlevel 1 (
  echo [ERROR] npm install failed.
  exit /b 1
)

:build_frontend
echo [INFO] Building frontend...
call npm --prefix prompt_vault/frontend run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)

echo [OK] Frontend build output: prompt_vault/frontend/dist
endlocal
