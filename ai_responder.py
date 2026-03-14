"""
ai_responder.py — Motor de IA basado en Groq (Llama 3)
Responde preguntas de postulación ultra rápido.
"""
import json
import time
import hashlib
from groq import Groq
from config import GROQ_API_KEY, cargar_perfil, FILTROS

import httpx
from limit_tracker import guardar_limites

_client = None
_perfil = None
_cache_relevancia = {}
_cache_preguntas = {}

def _on_response(response: httpx.Response):
    """Callback invocado por httpx para extraer del rate limit."""
    guardar_limites(response.headers)

def _get_client():
    global _client
    if _client is None:
        http_client = httpx.Client(event_hooks={'response': [_on_response]})
        _client = Groq(api_key=GROQ_API_KEY, http_client=http_client)
    return _client

def _esperar_si_es_necesario():
    """Consulta limit_tracker para ver si hay un retry_after pendiente."""
    from limit_tracker import obtener_limites
    limites = obtener_limites()
    if limites and limites.get("retry_after"):
        try:
            espera = int(limites["retry_after"])
            if espera > 0:
                print(f"    ⏳ Respetando pausa solicitada por Groq: {espera}s...")
                time.sleep(espera + 0.5)
        except: pass

def _get_perfil() -> dict:
    return cargar_perfil()

def _construir_contexto_perfil(perfil: dict) -> str:
    """Convierte el perfil JSON en texto para el prompt."""
    exp_texto = "\n".join(
        f"  - {e.get('cargo', 'Puesto')} en {e.get('empresa', 'Empresa')} ({e.get('periodo', e.get('fecha', 'No especificado'))}): {e.get('descripcion', '')}"
        for e in perfil.get("experiencia_laboral", [])
    )
    edu_texto = "\n".join(
        f"  - {ed['titulo']} en {ed['institucion']} ({ed['estado'] or 'No especificado'})"
        for ed in perfil.get("educacion", [])
    )
    
    habilidades = perfil.get("habilidades", [])
    habilidades_str = ", ".join(habilidades) if isinstance(habilidades, list) else str(habilidades)

    nombre = perfil.get('nombre_completo', 'Candidato')
    rut = perfil.get('rut', 'No especificado')
    email = perfil.get('email', 'No especificado')
    tel = perfil.get('telefono', 'No especificado')
    ubicacion = perfil.get('ubicacion', 'Chile')
    
    cargo_objetivo = FILTROS.get("carrera", "Profesional")
    resumen = perfil.get('resumen_profesional', 'Busco una oportunidad laboral.')

    base_conocimientos = perfil.get('base_conocimientos', [])
    if base_conocimientos:
        kb_lineas = []
        for item in base_conocimientos:
            skill = item.get('conocimiento', item.get('pregunta', 'Desconocido'))
            years = str(item.get('anos', item.get('respuesta', '0')))
            level = item.get('nivel', 'No especificado')
            kb_lineas.append(f"  - {skill}: {years} años, Nivel: {level}")
        kb_texto = "\n".join(kb_lineas)
    else:
        kb_texto = "  (Sin respuestas personalizadas)"

    # FAQs
    faq_lista = perfil.get("preguntas_frecuentes", [])
    if faq_lista:
        faq_texto = "\n".join(f"  - P: {f['pregunta']}\n    R: {f['respuesta']}" for f in faq_lista)
    else:
        faq_texto = "  (Sin FAQs registradas)"

    return f"""
PERFIL DEL CANDIDATO:
- Nombre: {nombre}
- RUT: {rut}
- Email: {email}
- Teléfono: {tel}
- Ubicación: {ubicacion}
- Cargo Objetivo: {cargo_objetivo}
- Resumen: {resumen}
- Habilidades: {habilidades_str}
- Experiencias:
{exp_texto}
- Educación:
{edu_texto}
- Disponibilidad: {perfil.get('preferencias', {}).get('disponibilidad', 'Inmediata')}
- Conocimientos Específicos:
{kb_texto}
- Preguntas Frecuentes Entrenadas (FAQ):
{faq_texto}
"""

def responder_pregunta(pregunta: str, descripcion_oferta: str = "") -> str:
    if pregunta in _cache_preguntas:
        return _cache_preguntas[pregunta]

    perfil = _get_perfil()
    contexto = _construir_contexto_perfil(perfil)
    ia_config = FILTROS.get("ia_config", {})
    exp_gen = ia_config.get("experiencia_general_anos", "1")
    l_no = ia_config.get("lista_no_posee", [])
    
    # Consolidamos habilidades que SÍ posee de la base de conocimientos del perfil
    kb = perfil.get("base_conocimientos", [])
    posee_str = ", ".join([f"{x.get('conocimiento','?')} ({x.get('anos','0')} años)" for x in kb]) if kb else "habilidades de tu perfil"
    no_posee_str = ", ".join([x['habilidad'] for x in l_no]) if l_no else "temas fuera de tu área"

    nacionalidad = ia_config.get("nacionalidad_ubicacion", "")
    nombre = perfil.get('nombre_completo', 'Candidato')
    rut = perfil.get('rut', 'no especificado')
    email = perfil.get('email', 'no especificado')
    telefono = perfil.get('telefono', 'no especificado')

    # Variación determinista para estabilidad de caché
    variaciones = [
        '"Aunque no he trabajado directamente con [herramienta], tengo base sólida y aprendo rápido."',
        '"No tengo experiencia previa en [herramienta], pero puedo adaptarme velozmente."',
        '"Si bien no he usado [herramienta] antes, manejo conceptos relacionados y estoy abierto a capacitarme."'
    ]
    v_idx = int(hashlib.md5(nombre.encode()).hexdigest(), 16) % len(variaciones)
    variacion = variaciones[v_idx]

    # Reglas
    r_nac = f'12. REGLA (Nacionalidad): Responde EXACTAMENTE: "{nacionalidad}".' if nacionalidad else ""
    r_rut = f'8. REGLA (RUT): Si piden RUT/Identificación, responde: "{rut}". Si solo piden "número", es el teléfono: {telefono}.'

    prompt = f"""Eres {nombre}, el candidato. Responde en primera persona.
{contexto}

REGLAS:
1. Sé breve (máximo 2 oraciones).
2. PRIORIDAD MÁXIMA: Si alguna de las "Preguntas Frecuentes Entrenadas (FAQ)" es similar a la PREGUNTA actual, usa esa respuesta como base o modelo exacto.
3. Si no sabes algo de la oferta, usa esta estructura: {variacion}
4. Si preguntan por habilidades en: {posee_str}, destaca tu experiencia.
5. Si preguntan por: {no_posee_str}, di que tienes 0 años pero buena base.
6. Experiencia general: {exp_gen} años.
{r_rut}
{r_nac}

OFERTA: {descripcion_oferta[:800]}
PREGUNTA: {pregunta}
RESPUESTA como {nombre}:"""

    for modelo in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]:
        for intento in range(2):
            try:
                _esperar_si_es_necesario()
                time.sleep(0.5)
                client = _get_client()
                res = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=modelo,
                    temperature=0.7,
                    max_tokens=200
                )
                ans = res.choices[0].message.content.strip()
                _cache_preguntas[pregunta] = ans
                return ans
            except Exception as e:
                if "429" in str(e): 
                    time.sleep(2)
                    break 
    return "Disponible para conversar más sobre mi experiencia en una entrevista."

def elegir_opcion_select(pregunta: str, opciones: list, descripcion_oferta: str = "") -> str:
    opciones_reales = [o for o in opciones if o.lower() not in ("", "selecciona", "seleccione", "select")]
    if not opciones_reales: return ""
    if len(opciones_reales) == 1: return opciones_reales[0]

    cache_key = f"select_{pregunta}_{hashlib.md5(str(opciones_reales).encode()).hexdigest()}"
    if cache_key in _cache_preguntas: return _cache_preguntas[cache_key]

    perfil = _get_perfil()
    contexto = _construir_contexto_perfil(perfil)
    
    prompt = f"""Tú eres el candidato:
{contexto}
PREGUNTA: {pregunta}
OPCIONES: {", ".join(opciones_reales)}
Responde SOLO con el JSON: {{"opcion": "TEXTO EXACTO"}}"""

    try:
        _esperar_si_es_necesario()
        client = _get_client()
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(res.choices[0].message.content)
        elegida = data.get("opcion", "")
        for o in opciones_reales:
            if o.lower() == elegida.lower():
                _cache_preguntas[cache_key] = o
                return o
    except: pass
    return opciones_reales[0]

def resumir_oferta(descripcion: str, empresa: str = "", url: str = "") -> str:
    if not descripcion or len(descripcion) < 10: return "Descripción no disponible."
    
    # Usar cache key basado en los 3 parámetros para evitar colisiones
    data_for_key = f"{descripcion}{empresa}{url}"
    key = hashlib.md5(data_for_key.encode()).hexdigest()
    if key in _cache_preguntas: return _cache_preguntas[key]

    contexto_extra = ""
    if empresa: contexto_extra += f"Empresa: {empresa}\n"
    if url: contexto_extra += f"Link: {url}\n"

    # Prompt más informativo para el resumen
    prompt = f"Resume esta oferta en 2 o 3 oraciones directas y profesionales. No repitas sueldo ni ubicación. Enfócate en la misión del cargo, responsabilidades clave y requisitos técnicos principales:\n\n{contexto_extra}\n{descripcion[:3000]}"
    
    for modelo in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"]:
        for intento in range(2):
            try:
                _esperar_si_es_necesario()
                client = _get_client()
                res = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=modelo,
                    temperature=0.3
                )
                ans = res.choices[0].message.content.strip().replace('"', '')
                _cache_preguntas[key] = ans
                return ans
            except Exception as e:
                # Handle rate limit explicitly if possible
                if "429" in str(e):
                    time.sleep(2)
                    break # try next model
    return "No se pudo resumir la oferta. (Excedido límite de peticiones)"

def evaluar_oferta_relevancia(titulo: str, descripcion: str) -> tuple[bool, str]:
    from config import FILTROS, cargar_perfil
    obj = FILTROS.get("carrera", "Profesional")
    desc = (descripcion or "")[:800]
    
    key = f"rel_{titulo}_{hashlib.md5(desc.encode()).hexdigest()}"
    if key in _cache_relevancia: return _cache_relevancia[key]

    # Palabras obligatorias (si se configuraron)
    palabras_obligatorias = FILTROS.get("palabras_obligatorias", [])
    filtro_palabras = ""
    if palabras_obligatorias:
        filtro_palabras = f"\nADEMÁS, la oferta DEBE mencionar al menos una de estas palabras clave: {', '.join(palabras_obligatorias)}. Si no las menciona, es NO RELEVANTE."
    
    prompt = f"""TAREA: Evalúa si esta oferta laboral es relevante para un buscador de empleo.

EL USUARIO BUSCA ACTIVAMENTE OFERTAS DE: "{obj}".
Esta es la intención de búsqueda PRIORITARIA. Aunque el candidato tenga experiencia en otras áreas, evalúa SOLO si la oferta calza con "{obj}".

OFERTA A EVALUAR:
- Título: {titulo}
- Descripción: {desc[:500]}
{filtro_palabras}

CRITERIO:
- Si el título o descripción se relaciona con "{obj}", responde relevante = true.
- Si no tiene relación directa con "{obj}", responde relevante = false.
- Una relación PARCIAL o SIMILAR es suficiente para ser relevante.

Responde ÚNICAMENTE con este JSON: {{"relevante": true/false, "razon": "breve explicación en español"}}"""

    try:
        _esperar_si_es_necesario()
        client = _get_client()
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(res.choices[0].message.content)
        result = (data.get("relevante", True), data.get("razon", "OK"))
        _cache_relevancia[key] = result
        return result
    except: return True, "Relevancia asumida por error"

def sintetizar_pensamiento() -> str:
    perfil = _get_perfil()
    nombre = perfil.get('nombre_completo', 'Candidato')
    prompt = f"Eres la conciencia de un bot de empleos para {nombre}. Genera un pensamiento breve (2 líneas) sobre tu estado actual."
    try:
        client = _get_client()
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.7
        )
        return res.choices[0].message.content.strip()
    except: return "Analizando nuevas oportunidades..."

def probar_conexion() -> str:
    try:
        client = _get_client()
        client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role":"user","content":"Hi"}], max_tokens=1)
        return "Conexión con Groq OK"
    except Exception as e: return f"Error: {e}"
