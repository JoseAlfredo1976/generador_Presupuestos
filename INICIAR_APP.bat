@echo off
title Generador de Presupuestos - Grupo Europa
color 0B
echo.
echo  ============================================================
echo   Generador de Presupuestos + Analisis IA - Grupo Europa
echo  ============================================================
echo.

rem --- API key de Anthropic (se lee de variable de entorno del sistema)
rem --- Si no esta configurada, puedes introducirla aqui:
rem --- set ANTHROPIC_API_KEY=sk-ant-...

cd /d "%~dp0"
echo  Iniciando servidor en http://localhost:5000
echo  (Pulsa Ctrl+C para detener)
echo.
py -3.12 app.py
pause
