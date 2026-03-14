import re

# Mock de lo que hace el bot
palabras_prohibidas = ["senior", "sr", "lider", "líder", "jefe", "gerente", "manager", "director", "lead", "experimentado", "ssr", "semi senior", "semisenior"]

test_titulos = [
    "Desarrollador Python Junior",
    "Senior Software Engineer",
    "Analista de Sistemas Semi Senior",
    "Jefe de Proyectos TI",
    "Soporte Técnico Nivel 1",
    "Lead Developer Backend",
    "Práctica Informática",
    "Gerente de Tecnología"
]

print("--- Probando Filtro de Palabras Prohibidas ---")
for titulo in test_titulos:
    titulo_lower = titulo.lower()
    prohibida_encontrada = None
    
    for p in palabras_prohibidas:
        # Usamos \b para que solo coincida con palabras completas
        if re.search(r'\b' + re.escape(p) + r'\b', titulo_lower):
            prohibida_encontrada = p
            break
    
    if prohibida_encontrada:
        print(f"❌ [OMITIDO] '{titulo}' -> Contiene palabra prohibida: '{prohibida_encontrada}'")
    else:
        print(f"✅ [ACEPTADO] '{titulo}'")
