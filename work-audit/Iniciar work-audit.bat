@echo off
rem ============================================================
rem  Lanzador de work-audit (auditor + bandeja + parte diario).
rem  Hacer doble clic en este archivo para iniciar la aplicacion.
rem
rem  En el primer arranque instala las dependencias de Python;
rem  en los siguientes arranca directamente y sin consola.
rem ============================================================
setlocal
cd /d "%~dp0"

rem --- Localizar Python --------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo.
    echo  No se ha encontrado Python en este equipo.
    echo  Instala Python 3.11 o superior desde https://www.python.org/downloads/
    echo  y marca la casilla "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

rem --- Instalar dependencias en el primer arranque -----------------------
"%PY%" -c "import PyQt6" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Primer arranque: instalando dependencias, espera un momento...
    echo.
    "%PY%" -m pip install -e .
    if errorlevel 1 (
        echo.
        echo  ERROR: no se pudieron instalar las dependencias.
        echo.
        pause
        exit /b 1
    )
)

rem --- Arrancar sin ventana de consola -----------------------------------
start "" "%PY%w" -m work_audit
endlocal
