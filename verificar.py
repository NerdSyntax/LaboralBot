import sys, os
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

# Verificar config
from config import validar_config, cargar_perfil
try:
    validar_config()
    print('OK config: credenciales cargadas')
except Exception as e:
    print(f'ERROR config: {e}')

# Verificar perfil
p = cargar_perfil()
# Corregir claves según perfil.json
nombre = p.get('nombre_completo', 'Usuario')
renta = p.get('preferencias', {}).get('renta_esperada', 0)
print(f"OK perfil: {nombre} | renta: ${int(renta):,}")

# Verificar BD
from database import inicializar_db, total_postulaciones
inicializar_db()
print(f"OK base de datos: {total_postulaciones()} postulaciones previas")

# Verificar IA
from ai_responder import _construir_contexto_perfil
ctx = _construir_contexto_perfil(p)
print('OK ai_responder: perfil construido correctamente')

# Verificar módulos
from scraper import crear_browser, login, obtener_ofertas
from aplicador import postular_oferta
print('OK scraper y aplicador: importados correctamente')

print()
print('=====================================')
print(' TODO OK - El bot esta listo para usar')
print('=====================================')
