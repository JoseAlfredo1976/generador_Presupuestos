@echo off
cd /d "%~dp0\.."
py -3.12 scripts\auditar_numeracion.py >> logs_auditoria.log 2>&1
