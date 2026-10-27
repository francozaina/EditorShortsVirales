@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "Editor_Shorts_Studio.py"
if %errorlevel% neq 0 (
    echo.
    echo [!] Ocurrio un error al ejecutar la aplicacion.
    pause
)
