@echo off
REM ---------------------------------------------------------------
REM  Avatar Interactivo - inicio
REM  Atajos:  D = vista previa camara   S = landmarks   ESC = salir
REM
REM  Si falta el entorno, se instala solo antes de arrancar.
REM  Para instalarlo sin arrancar:  scripts\install.bat
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0.."

set PY=venv\Scripts\python.exe

REM Todos los finales tempranos son fallos, asi que 1 es el valor por
REM defecto; solo main.py puede dejar otro.
set CODE=1

REM --- Si no hay venv, se prepara el entorno (network + varios minutos)
if not exist "%PY%" (
  echo No se ha encontrado el entorno virtual ^(venv/^).
  echo Se va a instalar todo lo necesario. Esto descarga paquetes y
  echo modelos de deteccion, asi que puede tardar unos minutos.
  echo.
  call scripts\install.bat --no-pause
  if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo preparar el entorno. No se puede arrancar.
    echo.
    pause
    goto :fin
  )
  echo.
)

REM --- Modelos de deteccion (por si se borraron)
if not exist "models\face_landmarker.task" goto :modelos
if not exist "models\hand_landmarker.task" goto :modelos
goto :verificar

:modelos
echo [1/2] Faltan los modelos de deteccion. Descargando...
"%PY%" scripts\download_models.py
if errorlevel 1 (
  echo.
  echo [ERROR] No se pudieron descargar los modelos.
  echo         Necesitas conexion a internet la primera vez.
  echo.
  pause
  goto :fin
)
echo.

:verificar
echo [2/2] Verificando entorno...
"%PY%" scripts\check_env.py
REM Si faltan paquetes o hay conflictos, NO se sigue: arrancar a ciegas
REM solo produce un ImportError incomprensible mas adelante.
if errorlevel 1 (
  echo.
  echo [ERROR] El entorno no esta listo. Ejecuta:  scripts\install.bat
  echo.
  pause
  goto :fin
)
echo.

echo Iniciando Avatar Interactivo...
echo Atajos: D = vista previa camara / S = landmarks / ESC = salir
echo.

"%PY%" -u src\main.py
set CODE=%ERRORLEVEL%

echo.
if "%CODE%"=="0" (
  echo Avatar cerrado correctamente.
) else (
  echo El avatar termino con codigo %CODE%.
)
echo.
pause
goto :fin

:fin
REM Mismo idioma: CODE se expande en la misma linea que endlocal, porque
REM separado el endlocal lo borraria antes de expandirse.
endlocal & exit /b %CODE%