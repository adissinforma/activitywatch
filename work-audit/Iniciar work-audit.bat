@echo off
rem Lanzador de work-audit (auditor + bandeja + parte diario).
rem Hacer doble clic en este archivo para iniciar la aplicacion.
cd /d "%~dp0"
start "" pythonw -m work_audit
