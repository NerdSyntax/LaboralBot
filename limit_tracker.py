import json
import os
from datetime import datetime

LIMITS_FILE = "groq_limits.json"

def guardar_limites(headers: dict):
    """Guarda los límites extraídos de los headers de una petición a Groq."""
    try:
        # Extraer headers de rate limit de Groq (ejemplo: x-ratelimit-remaining-tokens)
        limites = {
            "tokens_restantes_dia": headers.get("x-ratelimit-remaining-tokens"),
            "requests_restantes_dia": headers.get("x-ratelimit-remaining-requests"),
            "tokens_restantes_minuto": headers.get("x-ratelimit-remaining-tokens-per-minute", "N/A"),
            "modelo": headers.get("x-ratelimit-limit-model", "N/A"),
            "retry_after": headers.get("retry-after"),
            "ultima_actualizacion": datetime.now().isoformat()
        }
        
        # Guardar solo si encontramos datos válidos
        if limites["tokens_restantes_dia"] is not None:
             with open(LIMITS_FILE, 'w', encoding='utf-8') as f:
                 json.dump(limites, f, indent=4)
    except Exception as e:
        print(f"Error al guardar los límites de Groq: {e}")

def obtener_limites() -> dict:
    """Lee y retorna los últimos límites de Groq guardados."""
    if not os.path.exists(LIMITS_FILE):
        return None
        
    try:
        with open(LIMITS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def mostrar_estadisticas_groq(console):
    """Imprime el estado de cuota de la IA en la consola."""
    limites = obtener_limites()
    if limites and limites.get("tokens_restantes_dia"):
        from rich.panel import Panel
        from rich.text import Text
        
        tokens = limites.get("tokens_restantes_dia", "Desconocido")
        reqs = limites.get("requests_restantes_dia", "Desconocido")
        modelo = limites.get("modelo", "Desconocido")
        
        texto = Text()
        texto.append(f"🤖 Cuota de IA Groq (Modelo: {modelo})\n", style="bold cyan")
        texto.append(f"• Tokens restantes hoy: ", style="white")
        texto.append(f"{tokens}\n", style="bold yellow" if str(tokens) != "Desconocido" and int(tokens) < 10000 else "bold green")
        texto.append(f"• Peticiones restantes hoy: ", style="white")
        texto.append(f"{reqs}", style="bold green")
        
        panel = Panel(texto, border_style="cyan", title="Información de Límite de IA")
        console.print(panel)
        console.print()
