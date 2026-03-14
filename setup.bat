@echo off
echo ==========================================
echo    Instalador Automatico de LaboralBot
echo ==========================================
echo.

:: Comprobar si Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo Por favor, descarga e instala Python desde https://www.python.org/downloads/
    echo Asegurate de marcar la casilla "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual (opcional pero recomendado)...
python -m venv venv
call venv\Scripts\activate.bat

echo.
echo [2/4] Instalando dependencias desde requirements.txt...
pip install -r requirements.txt

echo.
echo [3/4] Instalando navegadores de Playwright...
playwright install chromium

echo.
echo [4/4] Preparando archivo .env...
if not exist .env (
    copy .env.example .env
    echo Archivo .env creado. Por favor, abre el archivo .env e ingresa tus datos.
) else (
    echo El archivo .env ya existe.
)

echo.
echo ==========================================
echo    Instalacion completada con exito!
echo ==========================================
echo Para iniciar el bot, asegurate de tener tu .env configurado y ejecuta:
echo python main.py
echo.
pause
