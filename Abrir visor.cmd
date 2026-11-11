@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "try { $null=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/estado' -TimeoutSec 2; exit 0 } catch { exit 1 }"
if errorlevel 1 powershell -NoProfile -Command "Start-Process -FilePath 'node' -ArgumentList 'servir_visor.cjs' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden"
powershell -NoProfile -Command "for($i=0;$i -lt 20;$i++){ try { $null=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/estado' -TimeoutSec 1; break } catch { Start-Sleep -Milliseconds 300 } }"
start "" http://127.0.0.1:8765/
