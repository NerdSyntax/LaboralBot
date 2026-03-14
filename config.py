"""
config.py — Configuración central del bot
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── Credenciales ──────────────────────────────────────────
DUOC_EMAIL    = os.getenv("DUOC_EMAIL", "")
DUOC_PASSWORD = os.getenv("DUOC_PASSWORD", "")
CHILETRABAJOS_EMAIL = os.getenv("CHILETRABAJOS_EMAIL", "")
CHILETRABAJOS_PASSWORD = os.getenv("CHILETRABAJOS_PASSWORD", "")
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
GETONBOARD_EMAIL = os.getenv("GETONBOARD_EMAIL", "")
GETONBOARD_PASSWORD = os.getenv("GETONBOARD_PASSWORD", "")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")

# ── URLs ──────────────────────────────────────────────────
BASE_URL   = "https://duoclaboral.cl"
LOGIN_URL  = "https://duoclaboral.cl/login"
# URL base para buscar ofertas (sin filtros, los agregamos en scraper.py)
OFERTAS_URL = "https://duoclaboral.cl/trabajo/trabajos-en-chile"

# ── Directorios ───────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PERFIL_PATH = os.path.join(BASE_DIR, "perfil.json")
FILTROS_PATH = os.path.join(BASE_DIR, "filtros.json")
DB_PATH     = os.path.join(BASE_DIR, "postulaciones.db")
SESSION_PATH = os.path.join(BASE_DIR, "session_state.json")
CV_PATH      = os.getenv("CV_PATH", os.path.join(BASE_DIR, "mi_cv.pdf"))


# ── Estructuras Iniciales ──────────────────────────────
_DEFAULT_FILTROS = {
    "palabras_clave": "", 
    "tipo_oferta": "",  
    "carrera": "",
    "region": "Santiago, Chile",
    "max_postulaciones_por_sesion": 10,
    "palabras_prohibidas": ["senior", "sr", "lider", "líder", "jefe", "gerente", "manager", "director", "lead", "ssr"],
    "instrucciones_ia": "",
    "ia_config": {
        "nacionalidad_ubicacion": "",
        "experiencia_general_anos": "0",
        "lista_posee": [],
        "lista_no_posee": []
    }
}

_DEFAULT_PERFIL = {
    "nombre_completo": "", "email": "", "telefono": "", "rut": "", "ubicacion": "",
    "resumen_profesional": "", "experiencia_laboral": [], "educacion": [],
    "habilidades": [], "preferencias": {"renta_esperada": "", "disponibilidad": "Inmediata"},
    "base_conocimientos": []
}

def cargar_filtros() -> dict:
    """Carga los filtros desde filtros.json o usa los default."""
    if os.path.exists(FILTROS_PATH):
        try:
            with open(FILTROS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return _DEFAULT_FILTROS
    return _DEFAULT_FILTROS

def guardar_filtros(filtros: dict):
    """Guarda los filtros en filtros.json."""
    with open(FILTROS_PATH, "w", encoding="utf-8") as f:
        json.dump(filtros, f, indent=4, ensure_ascii=False)

# Cargamos los filtros inicialmente
FILTROS = cargar_filtros()



def cargar_perfil() -> dict:
    """Carga el perfil del usuario desde perfil.json o usa el default si no existe."""
    if os.path.exists(PERFIL_PATH):
        try:
            with open(PERFIL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return _DEFAULT_PERFIL
    return _DEFAULT_PERFIL

def guardar_perfil(perfil: dict):
    """Guarda los cambios al perfil.json"""
    with open(PERFIL_PATH, "w", encoding="utf-8") as f:
        json.dump(perfil, f, indent=4, ensure_ascii=False)


def validar_config():
    """Verifica que las variables esenciales estén configuradas."""
    errores = []
    if not DUOC_EMAIL:
        errores.append("DUOC_EMAIL no está configurado en .env")
    if not DUOC_PASSWORD:
        errores.append("DUOC_PASSWORD no está configurado en .env")
    if not GROQ_API_KEY:
        errores.append("GROQ_API_KEY no está configurada en .env")

def actualizar_variable_env(key: str, value: str):
    """Actualiza o agrega una variable en el archivo .env."""
    env_path = os.path.join(BASE_DIR, ".env")
    lines = []
    found = False
    
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    with open(env_path, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip().startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                found = True
            else:
                f.write(line)
        if not found:
            if lines and not lines[-1].endswith("\n"):
                f.write("\n")
            f.write(f"{key}={value}\n")

    # Actualizar en el entorno actual para que los cambios se reflejen sin reiniciar
    os.environ[key] = value
    
    # Recargar variables globales si es necesario (esto es manual por ahora)
    if key == "DUOC_EMAIL": global DUOC_EMAIL; DUOC_EMAIL = value
    elif key == "DUOC_PASSWORD": global DUOC_PASSWORD; DUOC_PASSWORD = value
    elif key == "CHILETRABAJOS_EMAIL": global CHILETRABAJOS_EMAIL; CHILETRABAJOS_EMAIL = value
    elif key == "CHILETRABAJOS_PASSWORD": global CHILETRABAJOS_PASSWORD; CHILETRABAJOS_PASSWORD = value
    elif key == "LINKEDIN_EMAIL": global LINKEDIN_EMAIL; LINKEDIN_EMAIL = value
    elif key == "LINKEDIN_PASSWORD": global LINKEDIN_PASSWORD; LINKEDIN_PASSWORD = value
    elif key == "GETONBOARD_EMAIL": global GETONBOARD_EMAIL; GETONBOARD_EMAIL = value
    elif key == "CV_PATH": global CV_PATH; CV_PATH = value

def borrar_todas_las_credenciales_env():
    """Wipes all credential-related keys from .env and memory."""
    keys_to_wipe = [
        "DUOC_EMAIL", "DUOC_PASSWORD",
        "CHILETRABAJOS_EMAIL", "CHILETRABAJOS_PASSWORD",
        "LINKEDIN_EMAIL", "LINKEDIN_PASSWORD",
        "GETONBOARD_EMAIL", "GETONBOARD_PASSWORD",
        "GROQ_API_KEY", "CV_PATH"
    ]
    for key in keys_to_wipe:
        actualizar_variable_env(key, "")
