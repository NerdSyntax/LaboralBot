#!/bin/bash

echo "=========================================="
echo "   Instalador Automático de LaboralBot"
echo "=========================================="
echo ""

# Comprobar si Python está instalado
if ! command -v python3 &> /dev/null
then
    echo "[ERROR] python3 no está instalado. Por favor, instálalo primero."
    exit 1
fi

echo "[1/4] Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

echo ""
echo "[2/4] Instalando dependencias locales..."
pip install -r requirements.txt

echo ""
echo "[3/4] Instalando navegadores de Playwright..."
playwright install chromium

echo ""
echo "[4/4] Preparando archivo .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Archivo .env creado. Por favor, ábrelo y configura tus contraseñas."
else
    echo "El archivo .env ya existe."
fi

echo ""
echo "=========================================="
echo "    ¡Instalación completada con éxito!"
echo "=========================================="
echo "Para arrancar el bot, recuerda rellenar el .env y ejecuta:"
echo "source venv/bin/activate && python main.py"
echo ""
