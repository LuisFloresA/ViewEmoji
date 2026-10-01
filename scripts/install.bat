@echo off
REM ---------------------------------------------------------------
REM  Avatar Interactivo - instalacion
REM  Crea el venv, instala dependencias, arregla el conflicto de
REM  OpenCV y descarga los modelos. Se puede repetir sin riesgo.
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0.."

set CODE=1

REM Con --no-pause no espera a que se pulse una tecla. Lo usa run.bat,
REM que ya pone su propia pausa al final.
set PAUSE=1
if /i "%~1"=="--no-pause" set PAUSE=0

echo Buscando Python...

REM El launcher "py" permite pedir una version concreta; si no existe,
REM probamos con el "python" del PATH.
set BOOT=
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set BOOT=py -3

if not defined BOOT (
  python -c "import sys" >nul 2>&1
  if not errorlevel 1 set BOOT=python
)

if not defined BOOT (
  echo.
  echo [ERROR] No se ha encontrado Python en este equipo.
  echo.
  echo   1. Descargalo desde  https://www.python.org/downloads/
  echo   2. IMPORTANTE: marca la casilla "Add python.exe to PATH"
  echo      durante la instalacion.
  echo   3. Abre una consola nueva y vuelve a ejecutar este archivo.
  echo.
  if "%PAUSE%"=="1" pause
  goto :fin
)

%BOOT% scripts\bootstrap.py
set CODE=%ERRORLEVEL%

echo.
if "%CODE%"=="0" (
  echo Instalacion completada.
) else (
  echo La instalacion fallo. Revisa los mensajes de arriba.
)
echo.
if "%PAUSE%"=="1" pause

REM "endlocal & exit /b" en la MISMA linea: si van separadas, el endlocal
REM borra CODE antes de que se expanda y se devuelve un codigo vacio.
:fin
endlocal & exit /b %CODE%