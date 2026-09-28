@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Buscador de archivos en red local
cd /d "%~dp0"

rem --- localizar python -------------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo  [ERROR] No se encontro Python en este equipo.
    echo  Instalalo desde https://www.python.org/downloads/  ^(marca "Add to PATH"^)
    echo.
    pause
    exit /b 1
)

rem --- si se pasan argumentos, van directos al script -------------------------
if not "%~1"=="" (
    %PY% "%~dp0buscar_red.py" %*
    echo.
    pause
    exit /b %errorlevel%
)

:menu
cls
echo ============================================================================
echo                BUSCADOR DE ARCHIVOS EN LA RED LOCAL
echo ============================================================================
echo.
echo   1. Buscar archivos  (asistente: nombres, extension y segmentos)
echo   2. Busqueda rapida en 192.1.1 , 192.1.2 y 192.1.3
echo   3. Ver que equipos estan encendidos y sus carpetas compartidas
echo   4. Ayuda / todas las opciones
echo   5. Salir
echo.
set "OP="
set /p "OP=  Elige una opcion [1-5]: "

if "%OP%"=="1" goto asistente
if "%OP%"=="2" goto rapida
if "%OP%"=="3" goto listar
if "%OP%"=="4" goto ayuda
if "%OP%"=="5" exit /b 0
goto menu

:asistente
cls
%PY% "%~dp0buscar_red.py"
goto fin

:rapida
cls
echo  Puedes escribir hasta 3 nombres separados por coma. Ej: factura,nomina,contrato
set "NOMBRES="
set /p "NOMBRES=  Nombre(s) del archivo: "
set "EXTS="
set /p "EXTS=  Extension(es) separadas por coma (pdf,xlsx) o vacio: "

set "ARGS="
for %%N in (%NOMBRES%) do set "ARGS=!ARGS! -n "%%~N""
if not "%EXTS%"=="" set "ARGS=!ARGS! -e "%EXTS%""

if "%ARGS%"=="" (
    echo.
    echo  [!] Debes indicar al menos un nombre o una extension.
    echo.
    pause
    goto menu
)

for /f "tokens=1-4 delims=/-. " %%a in ("%DATE%") do set "HOY=%%d%%c%%b"
set "HORA=%TIME::=%"
set "HORA=%HORA: =0%"
set "SALIDA=resultados_%RANDOM%.csv"

echo.
%PY% "%~dp0buscar_red.py" !ARGS! -r 192.1.1 -r 192.1.2 -r 192.1.3 --csv "%SALIDA%"
goto fin

:listar
cls
%PY% "%~dp0buscar_red.py" --listar -r 192.1.1 -r 192.1.2 -r 192.1.3
goto fin

:ayuda
cls
%PY% "%~dp0buscar_red.py" --help
goto fin

:fin
echo.
pause
goto menu
