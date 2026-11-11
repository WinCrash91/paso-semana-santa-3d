@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" generar_paso.py
) else (
  python generar_paso.py
)
if errorlevel 1 pause
