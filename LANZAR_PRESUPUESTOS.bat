@echo off
setlocal ENABLEDELAYEDEXPANSION
title Generador Presupuestos Grupo Europa

set "APP_DIR=%~dp0"
set "URL=http://localhost:5000"
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

rem --- Comprobar si el servidor ya esta corriendo en :5000 ---
set "SRV_UP="
for /f "tokens=2 delims=:" %%P in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":5000 "') do (
  set "SRV_UP=1"
  goto :launched_check_done
)
:launched_check_done

if defined SRV_UP (
  echo Servidor ya activo en %URL%
) else (
  echo Arrancando servidor de presupuestos...
  pushd "%APP_DIR%"
  start "Presupuestos Server" /min cmd /c "py -3.12 app.py"
  popd

  rem --- Esperar a que el servidor responda (max ~20s) ---
  set /a TRIES=0
  :wait_loop
  set /a TRIES+=1
  powershell -NoProfile -Command "try{(Invoke-WebRequest -Uri '%URL%' -UseBasicParsing -TimeoutSec 1).StatusCode}catch{exit 1}" >nul 2>&1
  if !errorlevel! NEQ 0 (
    if !TRIES! GEQ 20 (
      echo No se pudo conectar al servidor.
      pause
      exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto wait_loop
  )
)

rem --- Abrir Chrome en modo app (sin barra de pestanas) ---
if exist "%CHROME%" (
  start "" "%CHROME%" --app=%URL% --new-window
) else (
  start "" "%URL%"
)

exit /b 0
