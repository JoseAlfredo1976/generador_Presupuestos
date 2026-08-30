@echo off
chcp 65001 >nul
title Publicar en Railway - Generador de Presupuestos
cd /d "%~dp0"
color 0B
echo ============================================================
echo   PUBLICAR EN RAILWAY - Generador de Presupuestos
echo ============================================================
echo.
echo  Se subira la version actual de esta carpeta a produccion.
echo  (Tarda alrededor de 90 segundos)
echo.
railway up --service generador_Presupuestos
echo.
echo ============================================================
echo  Si arriba pone SUCCESS -^> ya esta publicado.
echo  Web:  https://generadorpresupuestos-production-36b5.up.railway.app
echo.
echo  Si pide iniciar sesion, ejecuta antes:  railway login
echo ============================================================
echo.
pause
