@echo off
setlocal
cd /d "%~dp0\..\.."
pyinstaller --noconfirm --windowed --name PromptVault --paths . --distpath prompt_vault\\dist --workpath prompt_vault\\build --specpath prompt_vault prompt_vault\\app_entry.py
endlocal
