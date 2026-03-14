"""
main.py — Bot multi-portal de postulaciones automáticas
Portales soportados: DuocLaboral, ChileTrabajos (+ LinkedIn en el futuro)
Uso: python main.py
"""
import os
import sys
import json
import random
import time
import importlib
import unicodedata
from playwright.sync_api import sync_playwright, BrowserContext

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

import config
from config import validar_config, FILTROS, guardar_filtros, cargar_perfil, guardar_perfil, actualizar_variable_env, borrar_todas_las_credenciales_env
from database import inicializar_db, listar_postulaciones, total_postulaciones, ya_postule, registrar_postulacion, ya_omitida, registrar_omitida, listar_omitidas
from ai_responder import evaluar_oferta_relevancia, resumir_oferta, sintetizar_pensamiento, responder_pregunta
import limit_tracker
import shutil
import tkinter as tk
from tkinter import filedialog

console = Console()

# ─────────────────────────────────────────────────────────────────
#  UTILIDADES DE ARCHIVO
# ─────────────────────────────────────────────────────────────────

def seleccionar_archivo_pdf():
    """Abre un cuadro de diálogo nativo para seleccionar un archivo PDF."""
    try:
        root = tk.Tk()
        root.withdraw()  # Ocultar la ventana principal de tkinter
        root.attributes("-topmost", True)  # Asegurar que aparezca al frente
        
        file_path = filedialog.askopenfilename(
            title="Selecciona tu Currículum (PDF)",
            filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
        )
        root.destroy()
        return file_path
    except Exception as e:
        # Fallback si tkinter no está disponible o falla
        return None

# ─────────────────────────────────────────────────────────────────
#  BROWSER
# ─────────────────────────────────────────────────────────────────

def crear_browser(headless=False, force_clean=False):
    """
    Crea y retorna (playwright, browser, context, page).
    Si force_clean es True o falla la carga de sesión, inicia sin cookies.
    """
    from config import SESSION_PATH
    p = sync_playwright().start()
    
    # Argumentos para robustez y evasión
    browser_args = [
        "--start-maximized", 
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage"
    ]
    
    browser = p.chromium.launch(headless=headless, args=browser_args)
    
    context_args = {
        "no_viewport": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "locale": "es-ES",
        "timezone_id": "America/Santiago"
    }
    
    context = browser.new_context(**context_args)

    # Intentar cargar sesión a menos que se pida limpia
    if not force_clean and os.path.exists(SESSION_PATH):
        try:
            with open(SESSION_PATH, "r") as f:
                storage = json.load(f)
            cookies = storage.get("cookies", [])
            if cookies:
                context.add_cookies(cookies)
                console.print("[dim]  🍪 Cookies de sesión cargadas.[/dim]")
        except Exception as e:
            console.print(f"[yellow]  ⚠️  Error cargando session_state.json: {e}. Iniciando sesión limpia.[/yellow]")

    page = context.new_page()
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except Exception:
        pass
    return p, browser, context, page


# ─────────────────────────────────────────────────────────────────
#  MENÚ DE SELECCIÓN DE PORTAL
# ─────────────────────────────────────────────────────────────────

def seleccionar_portal() -> str:
    console.print(Panel.fit(
        "[bold cyan]🌐 Selecciona el Portal de Empleo[/bold cyan]",
        border_style="cyan"
    ))
    console.print("  [1] 🎓 DuocLaboral")
    console.print("  [2] 💼 ChileTrabajos")
    console.print("  [3] 🔗 LinkedIn")
    console.print("  [4] 🚀 Get on Board")
    console.print("  [0] 🔙 Volver atrás")
    console.print()
    opcion = input("  Portal [0-4]: ").strip()
    if opcion == "0":
        return ""
    portales = {"1": "duoclaboral", "2": "chiletrabajos", "3": "linkedin", "4": "getonboard"}
    return portales.get(opcion, "duoclaboral")


def obtener_instancia_portal(nombre: str, page, context):
    """Devuelve la instancia correcta según el portal elegido."""
    if nombre == "chiletrabajos":
        from portales.chiletrabajos.portal import ChileTrabajosPortal
        return ChileTrabajosPortal(page, context)
    elif nombre == "linkedin":
        from portales.linkedin.portal import LinkedinPortal
        return LinkedinPortal(page, context)
    elif nombre == "getonboard":
        from portales.getonboard.portal import GetOnBoardPortal
        return GetOnBoardPortal(page, context)
    else:  # Default: duoclaboral
        from portales.duoclaboral.portal import DuocLaboralPortal
        return DuocLaboralPortal(page, context)


# ─────────────────────────────────────────────────────────────────
#  MENÚ PRINCIPAL
# ─────────────────────────────────────────────────────────────────

def mostrar_menu(nombre_portal: str):
    import os
    os.system('cls' if os.name == 'nt' else 'clear')
    p_format = nombre_portal.upper()
    console.print(Panel(
        f"[bold white]Menú de Operaciones: {p_format}[/bold white]\n"
        f"[dim]Conectado y listo para postular.[/dim]",
        border_style="green",
        box=box.MINIMAL
    ))
    
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("Key", style="bold cyan")
    table.add_column("Desc", style="white")
    
    table.add_row("[0]", "⚙️  Ajustes de búsqueda de empleo (IMPORTANTE)")
    table.add_row("[1]", "🚀 Iniciar búsqueda (Revisión Manual)")
    table.add_row("[2]", "⚡ Modo Automático (Sin confirmación)")
    table.add_row("[5]", "🔍 Escaneo Silencioso (Sin postular)")
    table.add_row("[6]", "🔄 Cambiar de Portal")
    table.add_row("[9]", "❌ Salir")
    
    console.print(table)
    return input("\n  Comando: ").strip()

def validar_region_portal(nombre_portal, ubicacion):
    """Detecta si la región/ciudad ingresada es compatible con el portal."""
    if not ubicacion or ubicacion.lower() == "cualquiera":
        return True, ""
        
    # Mapeo de ciudades comunes a regiones de DuocLaboral
    CITY_TO_REGION = {
        "chillan": "XVI Región de Ñuble",
        "chillán": "XVI Región de Ñuble",
        "santiago": "Región Metropolitana",
        "conce": "VIII Región del Bío - Bío",
        "concepcion": "VIII Región del Bío - Bío",
        "concepción": "VIII Región del Bío - Bío",
        "valpo": "V Región de Valparaíso",
        "valparaiso": "V Región de Valparaíso",
        "valparaíso": "V Región de Valparaíso",
        "temuco": "IX Región de la Araucanía",
        "antofa": "II Región de Antofagasta",
        "antofagasta": "II Región de Antofagasta",
        "iquique": "I Región de Tarapacá",
        "arica": "XV Región de Arica y Parinacota",
        "rancagua": "VI Región del Lib. Gral. Bernardo O´Higgins",
        "talca": "VII Región del Maule",
        "puerto montt": "X Región de Los Lagos",
        "punta arenas": "XII Región de Magallanes",
        "coyhaique": "XI Región de Aysén",
        "valdivia": "XIV Región de Los Ríos",
        "copiapo": "III Región de Atacama",
        "copiapó": "III Región de Atacama",
        "la serena": "IV Región de Coquimbo",
        "coquimbo": "IV Región de Coquimbo"
    }

    if nombre_portal == "duoclaboral":
        from constantes import DUOC_REGIONES, DUOC_COMUNAS
        if ubicacion not in DUOC_REGIONES and ubicacion not in DUOC_COMUNAS:
            sugerencia = CITY_TO_REGION.get(ubicacion.lower())
            msg = f"⚠️  [bold yellow]¡ADVERTENCIA![/bold yellow] DuocLaboral usa opciones predefinidas. La ubicación '{ubicacion}' no figura en su lista oficial."
            if sugerencia:
                msg += f"\n     💡 [bold cyan]¿Quisiste decir '{sugerencia}'?[/bold cyan]"
            else:
                msg += " Podría devolver CERO resultados o ignorar el filtro."
            return False, msg
    elif nombre_portal == "chiletrabajos":
        from constantes import CT_CIUDADES
        if ubicacion not in CT_CIUDADES:
            return False, f"⚠️  [bold red]¡ADVERTENCIA![/bold red] ChileTrabajos filtra por CIUDADES oficiales. '{ubicacion}' no figura en su base de datos. Te recomendamos cambiar a una ciudad específica desde las opciones (ej: Temuco, Concepción, Santiago)."
            
    return True, ""

def menu_seleccionar_opcion(dict_opciones, titulo, tipo_busqueda="cargo"):
    """Muestra una lista de opciones con filtrado progresivo y selección personalizada."""
    if tipo_busqueda == "region":
        col_name = "Región"
        ejemplo_txt = "💡 Ejemplo: escribe \"metro\" o \"valpo\" en lugar de la palabra completa."
        aviso_txt = "⚠️  Importante: Es mejor buscar por pedazos pequeños sin tildes."
        input_manual = "✏️  Ingresa la región personalizada que buscas: "
        aviso_notfound = "Es recomendado buscar y seleccionar una región de la lista oficial."
        usar_manual = "⚠️  Usar \"{}\" como región personalizada"
        letra_pers = "m región personalizada"
    elif tipo_busqueda == "ciudad":
        col_name = "Ciudad"
        ejemplo_txt = "💡 Ejemplo: escribe \"temu\" o \"concep\" en lugar de la palabra completa."
        aviso_txt = "⚠️  Importante: Es mejor buscar por pedazos pequeños sin tildes."
        input_manual = "✏️  Ingresa la ciudad personalizada que buscas: "
        aviso_notfound = "Es recomendado buscar y seleccionar una ciudad de la lista oficial para evitar errores de búsqueda."
        usar_manual = "⚠️  Usar \"{}\" como ciudad personalizada"
        letra_pers = "m ciudad personalizada"
    elif tipo_busqueda == "comuna":
        col_name = "Comuna"
        ejemplo_txt = "💡 Ejemplo: escribe \"quili\" o \"puen\" en lugar de la palabra completa."
        aviso_txt = "⚠️  Importante: Es mejor buscar por pedazos pequeños sin tildes."
        input_manual = "✏️  Ingresa la comuna personalizada que buscas: "
        aviso_notfound = "Es recomendado buscar y seleccionar una comuna de la lista oficial."
        usar_manual = "⚠️  Usar \"{}\" como comuna personalizada"
        letra_pers = "m comuna personalizada"
    elif tipo_busqueda == "modalidad":
        col_name = "Modalidad"
        ejemplo_txt = "💡 Ejemplo: escribe \"remot\" o \"hibrid\"."
        aviso_txt = "⚠️  Importante: Selecciona de la lista oficial."
        input_manual = "✏️  Ingresa la modalidad personalizada: "
        aviso_notfound = "Es recomendado buscar y seleccionar una modalidad oficial."
        usar_manual = "⚠️  Usar \"{}\" como modalidad personalizada"
        letra_pers = "m modalidad pers."
    else:
        col_name = "Cargo / Carrera"
        ejemplo_txt = "💡 Ejemplo: escribe \"ingen\" o \"mark\" en lugar de la palabra completa."
        aviso_txt = "⚠️  Importante: Es mejor buscar por pedazos pequeños y sin tildes...\n      Si tú pides \"marketing\" pero la lista dice \"m/marketing\", no lo encontrará exacto."
        input_manual = "✏️  Ingresa el cargo personalizado que buscas: "
        aviso_notfound = "Es altamente recomendado buscar y seleccionar un cargo de la lista oficial para evitar errores."
        usar_manual = "⚠️  Usar \"{}\" como cargo personalizado de todos modos"
        letra_pers = "m cargo personalizado"

    llaves_base = sorted(k for k in dict_opciones)
    llaves_actuales = llaves_base.copy()
    filtro_activo = ""
    max_mostrar = 12
    limite_mostrar = max_mostrar

    while True:
        console.clear()
        total = len(llaves_actuales)

        # ── Encabezado con estado del filtro ─────────────────────────
        if filtro_activo:
            console.print(Panel(
                f"[bold cyan]{titulo}[/bold cyan]\n"
                f"  [on dark_orange3] FILTRO: \"{filtro_activo}\" [/on dark_orange3]  "
                f"[dim]{total} resultado(s) de {len(llaves_base)}[/dim]",
                border_style="yellow", padding=(0, 1)
            ))
        else:
            console.print(Panel(
                f"[bold cyan]{titulo}[/bold cyan]  [dim]— {len(llaves_base)} opciones disponibles[/dim]",
                border_style="cyan", padding=(0, 1)
            ))

        console.print()

        # ── Tabla ─────────────────────────────────────────────────────
        t = Table(box=box.SIMPLE_HEAVY, show_header=True,
                  header_style="bold white on blue", padding=(0, 1))
        t.add_column("N°", style="bold yellow", justify="right", width=4)
        t.add_column(col_name, style="white")

        for i, llave in enumerate(llaves_actuales[:limite_mostrar]):
            t.add_row(str(i + 1), llave)

        if total > limite_mostrar:
            t.add_row("[dim]…[/dim]",
                      f"[dim]+ {total - limite_mostrar} más — escribe letras para filtrar o 't' para ver todos[/dim]")

        console.print(t)

        # ── Leyenda de controles ────────────────────────────────────────────────
        console.print(
            "  [on black] [bold yellow]🔍 Escribe letras[/bold yellow] para filtrar │ "
            "[bold green]Nº[/bold green] para elegir │ "
            "[bold blue]t[/bold blue] mostrar todos │ "
            f"[bold magenta]m[/bold magenta] {letra_pers} │ "
            "[bold white]x[/bold white] limpiar filtro │ "
            "[bold red]0[/bold red] cancelar [/on black]"
        )
        console.print(f"  [dim]  {ejemplo_txt}[/dim]\n  [dim]  {aviso_txt}[/dim]")
        console.print()

        entrada = input("  › ").strip()

        if not entrada:
            continue
        if entrada == "0":
            return None
        if entrada.lower() == "x":
            llaves_actuales = llaves_base.copy()
            filtro_activo = ""
            limite_mostrar = max_mostrar
            continue
        if entrada.lower() == "t":
            limite_mostrar = len(llaves_actuales)
            continue
        if entrada.lower() == "m":
            console.print()
            manual = input(f"  {input_manual}").strip()
            if manual:
                return manual
            continue

        if entrada.isdigit():
            idx = int(entrada) - 1
            if 0 <= idx < min(total, limite_mostrar):
                seleccion = llaves_actuales[idx]
                console.print(f"\n  [bold green]✅[/bold green] [bold white]{seleccion}[/bold white]\n")
                time.sleep(0.8)
                return seleccion
            else:
                console.print(f"  [red]❌ Número fuera de rango (1–{min(total, limite_mostrar)}).[/red]")
                time.sleep(1)
                continue

        # ── Búsqueda por texto (insensible a tildes y mayúsculas) ──────
        def _norm(s): return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
        resultados = [k for k in llaves_base if _norm(entrada) in _norm(k)]
        if not resultados:
            console.print(f"\n  [yellow]⚠️  Sin coincidencias para [bold]\"{entrada}\"[/bold].[/yellow]")
            console.print(f"  [dim]{aviso_notfound}[/dim]")
            console.print("\n  [cyan]💡 ¿Qué deseas hacer?[/cyan]")
            console.print("  [1] 🔙 Volver a buscar (Recomendado)")
            console.print(f"  [2] {usar_manual.format(entrada)}")
            
            opc = input("\n  Opción [1/2] (Enter = Volver): ").strip()
            if opc == "2":
                return entrada
            
            filtro_activo = ""
            llaves_actuales = llaves_base.copy()
        else:
            filtro_activo = entrada
            llaves_actuales = resultados
            limite_mostrar = max_mostrar

def menu_ajustar_filtros_antes_de_buscar(nombre_portal):
    """Permite al usuario verificar y cambiar Carrera, Región, Comuna y Modalidad antes de iniciar."""
    from constantes import DUOC_CARRERAS, DUOC_REGIONES, DUOC_COMUNAS, DUOC_MODALIDADES
    
    while True:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        carrera = FILTROS.get("carrera", "Ingeniería en informática")
        region = FILTROS.get("region", "Región Metropolitana")
        comuna = FILTROS.get("comuna", "Cualquiera")
        ciudad = FILTROS.get("ciudad", "Santiago")
        modalidad = FILTROS.get("modalidad", "Cualquiera")
        
        is_ct = (nombre_portal == "chiletrabajos")
        ubicacion_validar = ciudad if is_ct else region
        ok, msg = validar_region_portal(nombre_portal, ubicacion_validar)
        
        panel_content = (
            f"  [bold cyan]⚙️  AJUSTES DE BÚSQUEDA DE EMPLEO (IMPORTANTE) - {nombre_portal.upper()}[/bold cyan]\n\n"
            f"  🎓 Carrera:      [green]{carrera}[/green]\n"
        )
        
        # Mostrar ambos pero destacar cuál aplica para el portal actual
        if is_ct:
            panel_content += f"  🏙️  Ciudad:      [bold green]{ciudad}[/bold green] (Aplica para ChileTrabajos)\n"
            panel_content += f"  [dim]📍 Región:      {region} (No aplica aquí)[/dim]\n"
            panel_content += f"  [dim]🏘️  Comuna:      {comuna} (No aplica aquí)[/dim]\n"
        else:
            panel_content += f"  📍 Región:      [bold green]{region}[/bold green] (Aplica para DuocLaboral)\n"
            panel_content += f"  🏘️  Comuna:      [bold green]{comuna}[/bold green] (Acota la Región en Duoc)\n"
            panel_content += f"  [dim]🏙️  Ciudad:      {ciudad} (No aplica aquí)[/dim]\n"
            
        panel_content += f"  💻 Modalidad:  [green]{modalidad}[/green]\n"
        if not ok:
            panel_content += f"\n  {msg}"
            
        console.print(Panel(
            panel_content,
            title="[bold white]Filtros de Búsqueda[/bold white]",
            border_style="cyan"
        ))
        
        console.print(f"\n  [1] 🎓 Cambiar Carrera")
        console.print(f"  [2] 📍 Cambiar Región de Búsqueda (Ej: RM, Valparaíso)")
        console.print(f"  [3] 🏘️  Cambiar Comuna de Búsqueda (Acotará la búsqueda en DuocLaboral)")
        console.print(f"  [4] 🏙️  Cambiar Ciudad de Búsqueda (Ej: Temuco - Sólo para ChileTrabajos)")
        console.print(f"  [5] 💻 Cambiar Modalidad (Ej: Remoto, Híbrido)")
        console.print("  [0] ✅ Confirmar y Continuar")
        
        opc = input("\n  Selecciona: ").strip()
        if opc == "1":
            # Cambiar carrera
            nueva = menu_seleccionar_opcion(DUOC_CARRERAS, "Selecciona tu Carrera Objetivo")
            if nueva:
                FILTROS["carrera"] = nueva
                # Sincronizar cargo_objetivo en el perfil también
                _perfil = cargar_perfil()
                _perfil["cargo_objetivo"] = nueva
                guardar_perfil(_perfil)
                guardar_filtros(FILTROS)
        elif opc == "2":
            # Cambiar region siempre
            opciones_reg = {"Cualquiera": ""}
            opciones_reg.update(DUOC_REGIONES)
            nueva = menu_seleccionar_opcion(opciones_reg, "Selecciona la Región", "region")
            if nueva:
                FILTROS["region"] = nueva
                _perfil = cargar_perfil()
                if nueva != "Cualquiera" and nueva:
                    _perfil["ubicacion"] = nueva
                guardar_perfil(_perfil)
                guardar_filtros(FILTROS)
        elif opc == "3":
            # Cambiar comuna siempre
            opciones_com = {"Cualquiera": ""}
            opciones_com.update(DUOC_COMUNAS)
            nueva = menu_seleccionar_opcion(opciones_com, "Selecciona la Comuna", "comuna")
            if nueva:
                FILTROS["comuna"] = nueva
                _perfil = cargar_perfil()
                if nueva != "Cualquiera" and nueva:
                    reg_actual = FILTROS.get("region", "")
                    _perfil["ubicacion"] = f"{nueva}, {reg_actual}" if reg_actual else nueva
                guardar_perfil(_perfil)
                guardar_filtros(FILTROS)
        elif opc == "4":
            # Cambiar ciudad siempre
            from constantes import CT_CIUDADES
            nueva = menu_seleccionar_opcion(CT_CIUDADES, "Selecciona la Ciudad (ChileTrabajos)", "ciudad")
            if nueva:
                FILTROS["ciudad"] = nueva
                _perfil = cargar_perfil()
                if nueva != "Cualquiera" and nueva:
                    _perfil["ubicacion"] = nueva
                guardar_perfil(_perfil)
                guardar_filtros(FILTROS)
        elif opc == "5":
            # Cambiar modalidad siempre
            opciones_mod = {"Cualquiera": ""}
            opciones_mod.update(DUOC_MODALIDADES)
            nueva = menu_seleccionar_opcion(opciones_mod, "Selecciona Modalidad", "modalidad")
            if nueva:
                FILTROS["modalidad"] = nueva
                guardar_filtros(FILTROS)
        elif opc == "0":
            break


def _procesar_oferta_individual(context, nombre_portal, oferta_basica, enviadas, max_postulaciones, modo_revision=True) -> str:
    """
    Procesa una oferta individual en una pestaña nueva.
    Retorna el estado de la postulación ('enviada', 'saltada', 'error', etc.).
    """
    oferta_id = oferta_basica.get("id", "")
    titulo_basico = oferta_basica.get("titulo", "")[:60]
    url_oferta = oferta_basica.get("url", "")

    console.print(Panel(
        f"[bold yellow]OFERTA #{enviadas+1}[/bold yellow] | [bold white]{titulo_basico}[/bold white]\n"
        f"[dim]ID: {oferta_id}[/dim]\n"
        f"🔗 [bold cyan]{url_oferta}[/bold cyan]",
        title=f"[cyan]{nombre_portal}[/cyan]",
        border_style="grey50"
    ))

    tab = context.new_page()
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(tab)
    except: pass

    try:
        portal_tab = obtener_instancia_portal(nombre_portal, tab, context)
        tab.goto(url_oferta, timeout=60000)
        
        # Obtener detalle
        detalle = portal_tab.obtener_detalle_oferta(url_oferta)
        
        # --- FILTROS AVANZADOS TRAS DETALLE ---
        # 1. Lista Negra de Empresas
        empresa = detalle.get("empresa", "").lower()
        empresas_negras = FILTROS.get("empresas_prohibidas", [])
        if any(en.lower() in empresa for en in empresas_negras):
            console.print(f"  [red]⏭  Saltando Empresa Bloqueada: {detalle.get('empresa')}[/red]")
            registrar_omitida(oferta_id, detalle.get('titulo', titulo_basico), detalle.get('empresa'), url_oferta, "empresa_bloqueada", portal=nombre_portal)
            return "empresa_bloqueada"

        # Filtro de relevancia IA
        relevante, razon = evaluar_oferta_relevancia(detalle.get('titulo', titulo_basico), detalle.get('descripcion', ""))
        if not relevante:
            console.print(f"  [yellow]⏭  Saltando (IA): {razon}[/yellow]")
            registrar_omitida(oferta_id, detalle.get('titulo', titulo_basico), detalle.get('empresa', ""), url_oferta, "no_relevante", portal=nombre_portal)
            return "no_relevante"

        # --- VISUALIZACIÓN DE DETALLES ---
        metadata = detalle.get("metadata", {})
        if metadata:
            t_meta = Table(show_header=False, box=box.ROUNDED, border_style="cyan", title="[bold cyan]Detalles de la Oferta[/bold cyan]")
            t_meta.add_column("K", style="bold cyan")
            t_meta.add_column("V")
            for k, v in metadata.items():
                t_meta.add_row(k, v)
            console.print(t_meta)

        # Resumen IA (opcional)
        console.print("  [dim]Generando resumen con IA...[/dim]")
        try:
            resumen = resumir_oferta(
                detalle.get("descripcion", ""), 
                empresa=detalle.get("empresa", ""), 
                url=url_oferta
            )
            detalle["resumen_ia"] = resumen
            console.print(Panel(f"[italic white]{resumen}[/italic white]", title="[cyan]Resumen IA[/cyan]", border_style="cyan"))
        except: pass

        # Postular
        console.print("  [green]✅ Oferta relevante. Iniciando postulación...[/green]")
        estado = portal_tab.postular_oferta(oferta_basica, detalle, modo_revision=modo_revision)
        
        # Registrar en BD (incluyendo respuestas si existen)
        respuestas_str = detalle.get("answers_generated", "") 
        registrar_postulacion(
            oferta_id, 
            detalle.get('titulo', titulo_basico), 
            detalle.get('empresa', ""), 
            url_oferta, 
            estado, 
            respuestas=str(respuestas_str),
            portal=nombre_portal
        )

        if estado == "enviada":
            console.print(f"  [bold green]🚀 Postulación enviada correctamente![/bold green]")
        elif estado not in ("saltada", "duplicado", "revision"):
            # Capturar snapshot de error
            try:
                timestamp = int(time.time())
                snapshot_path = f"error_{nombre_portal}_{oferta_id}_{timestamp}.html"
                with open(snapshot_path, "w", encoding="utf-8") as f:
                    f.write(tab.content())
                console.print(f"  [red]📸 Snapshot de error guardado: {snapshot_path}[/red]")
            except: pass
            
        return estado

    except Exception as e:
        console.print(f"  [red]❌ Error procesando oferta {oferta_id}: {e}[/red]")
        return "error_proceso"
    finally:
        try: tab.close()
        except: pass
        _pausa(0.5, 1.5)

# ─────────────────────────────────────────────────────────────────
#  FLUJO PRINCIPAL DE POSTULACIÓN
# ─────────────────────────────────────────────────────────────────

def _pausa(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))


def run_bot(nombre_portal: str, modo_revision: bool = True):
    console.rule("[yellow]Iniciando bot[/yellow]")

    try:
        validar_config()
    except EnvironmentError as e:
        console.print(f"[red]❌ Error de configuración:\n{e}[/red]")
        console.print("\n[dim]Copia .env.example como .env y completa tus credenciales.[/dim]")
        return

    # Le damos a max_postulaciones un número arbitrariamente grande si el usuario lo pone en 0 o no importa
    max_postulaciones = FILTROS.get("max_postulaciones_por_sesion", 99999)
    if max_postulaciones == 0:
        max_postulaciones = 99999
    
    enviadas = 0
    errores = 0

    intentos_sesion = 0
    max_intentos_sesion = 2

    while intentos_sesion < max_intentos_sesion and enviadas < max_postulaciones:
        intentos_sesion += 1
        
        # Cargamos perfil y filtros actualizados
        perfil = cargar_perfil()
        carrera = FILTROS.get("carrera", "Ingeniería en informática")
        
        region_filtro = FILTROS.get("region", "").strip()
        comuna_filtro = FILTROS.get("comuna", "Cualquiera")
        ciudad_filtro = FILTROS.get("ciudad", "Santiago").strip()
        modalidad_filtro = FILTROS.get("modalidad", "Cualquiera")
        
        # Determinar la ubicación principal enviada al portal
        if nombre_portal == "chiletrabajos":
            ubicacion = ciudad_filtro
        else:
            ubicacion = region_filtro if region_filtro else perfil.get("ubicacion", "Región Metropolitana")
            if comuna_filtro and comuna_filtro != "Cualquiera":
                ubicacion = comuna_filtro
        
        loc_label = "Ciudad" if nombre_portal == "chiletrabajos" else "Región"
        loc_disp = ciudad_filtro if nombre_portal == "chiletrabajos" else region_filtro
        
        panel_content = (
            f"[bold cyan]Portal activo:[/bold cyan] {nombre_portal.capitalize()}\n"
            f"[bold cyan]Objetivo:[/bold cyan]      {carrera}\n"
            f"[bold cyan]{loc_label}:[/bold cyan]        {loc_disp}\n"
        )
        if nombre_portal != "chiletrabajos":
            panel_content += f"[bold cyan]Comuna:[/bold cyan]        {comuna_filtro}\n"
            
        panel_content += (
            f"[bold cyan]Modalidad:[/bold cyan]     {modalidad_filtro}\n"
            f"[bold cyan]Modo:[/bold cyan]          {'[yellow]Revisión Manual[/yellow]' if modo_revision else '[red]Automático[/red]'}"
        )
        
        console.print(Panel(
            panel_content,
            title="🚀 CENTRO DE OPERACIONES",
            border_style="green",
            box=box.ROUNDED
        ))
        
        console.print(f"\n[bold blue]🌀 Desplegando núcleos en {nombre_portal} (Intento {intentos_sesion})...[/bold blue]")
        
        # Iniciar browser (limpio si es el segundo intento)
        p, browser, context, page = crear_browser(headless=False, force_clean=(intentos_sesion > 1))

        try:
            # Instanciar el portal dinámicamente
            portal = obtener_instancia_portal(nombre_portal, page, context)
            console.print(f"[bold cyan]Portal activo: {portal.nombre}[/bold cyan]")

            # Login
            console.print("[cyan]🔑 Iniciando sesión...[/cyan]")
            if not portal.login():
                console.print("[red]❌ No se pudo iniciar sesión. Verifica tus credenciales.[/red]")
                try:
                    browser.close()
                    p.stop()
                except: pass
                
                if intentos_sesion >= max_intentos_sesion:
                    return
                continue

            # Aplicar filtros de búsqueda
            palabras_prohibidas = FILTROS.get("palabras_prohibidas", [])
            
            console.print(f"\n[bold magenta]⚙️ Aplicando filtros de búsqueda: {carrera} | {ubicacion}[/bold magenta]")
            portal.aplicar_filtros_avanzados(carrera, ubicacion)

            # Recorrer páginas de resultados (infinitamente hasta que se acaben)
            paginas_totales = 999
            for num_pagina in range(1, paginas_totales + 1):
                if enviadas >= max_postulaciones:
                    break

                console.print(f"\n[bold cyan]📄 Explorando página {num_pagina}...[/bold cyan]")
                tarjetas_datos = portal.obtener_ofertas(paginas=paginas_totales, num_pagina_actual=num_pagina)

                if not tarjetas_datos:
                    console.print("  [yellow]⚠️ No hay más ofertas en esta sección.[/yellow]")
                    break

                for idx, oferta_basica in enumerate(tarjetas_datos, 1):
                    if enviadas >= max_postulaciones:
                        break

                    oferta_id = oferta_basica.get("id", "")
                    titulo_basico = oferta_basica.get("titulo", "")[:60]
                    url_oferta = oferta_basica.get("url", "")
                    
                    # Filtros rápidos
                    if ya_postule(oferta_id) or ya_omitida(oferta_id):
                        continue

                    # Palabras prohibidas
                    titulo_lower = titulo_basico.lower()
                    prohibida_encontrada = None
                    import re
                    for palabra in palabras_prohibidas:
                        if re.search(r'\b' + re.escape(palabra) + r'\b', titulo_lower):
                            prohibida_encontrada = palabra
                            break
                    if prohibida_encontrada:
                        console.print(f"  [red]⏭  Omitiendo '{titulo_basico}' (prohibida: {prohibida_encontrada})[/red]")
                        registrar_omitida(oferta_id, titulo_basico, "", url_oferta, "palabra_prohibida", portal=nombre_portal)
                        continue # Added continue here to match the original logic flow

                    # Palabras obligatorias
                    obligatorias = FILTROS.get("palabras_obligatorias", [])
                    if obligatorias:
                        encontrada = False
                        for ob in obligatorias:
                            if re.search(r'\b' + re.escape(ob) + r'\b', titulo_lower):
                                encontrada = True
                                break
                        if not encontrada:
                            console.print(f"  [yellow]⏭  Omitiendo '{titulo_basico}' (falta palabra obligatoria)[/yellow]")
                            registrar_omitida(oferta_id, titulo_basico, "", url_oferta, "falta_palabra_obligatoria", portal=nombre_portal)
                            continue

                    # Procesar oferta individualmente
                    estado = _procesar_oferta_individual(context, nombre_portal, oferta_basica, enviadas, max_postulaciones, modo_revision=modo_revision)
                    if estado == "enviada":
                        enviadas += 1
                    elif estado in ("error", "error_proceso", "error_boton"):
                        errores += 1
                    elif estado == "revision":
                        # Detener bot si estamos en revisión manual y el usuario quiere ver algo
                        pass

            # Si terminamos el ciclo de páginas sin crash crítico, salimos de los intentos
            break

        except Exception as e:
            console.print(f"[bold red]💥 Error crítico en la sesión: {e}[/bold red]")
            if intentos_sesion >= max_intentos_sesion:
                console.print("[red]💀 Se agotaron los intentos de recuperación.[/red]")
            else:
                console.print("[yellow]🔄 Intentando recuperar sesión limpia...[/yellow]")
        finally:
            try:
                browser.close()
                p.stop()
            except: pass

    # Resumen
    console.rule("[yellow]Resumen de la Sesión[/yellow]")
    console.print(f"  ✅ Postulaciones enviadas : [green]{enviadas}[/green]")
    console.print(f"  ❌ Errores               : [red]{errores}[/red]")
    console.print(f"  📊 Total histórico en DB : {total_postulaciones()}")


# ─────────────────────────────────────────────────────────────────
#  SOLO ESCANEAR (sin postular)
# ─────────────────────────────────────────────────────────────────

def solo_escanear(nombre_portal: str):
    console.rule("[cyan]Modo escaneo[/cyan]")
    try:
        validar_config()
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        return

    inicializar_db()
    p, browser, context, page = crear_browser(headless=False)

    try:
        portal = obtener_instancia_portal(nombre_portal, page, context)
        if not portal.login():
            return

        carrera = FILTROS.get("carrera", "Ingeniería en informática")
        if nombre_portal == "chiletrabajos":
            ubicacion = FILTROS.get("ciudad", "Santiago")
        else:
            region_f = FILTROS.get("region", "")
            comuna_f = FILTROS.get("comuna", "Cualquiera")
            if comuna_f and comuna_f != "Cualquiera":
                ubicacion = comuna_f
            else:
                ubicacion = region_f if region_f else "Región Metropolitana"
                
        portal.aplicar_filtros_avanzados(carrera, ubicacion)
        ofertas = portal.obtener_ofertas(paginas=999, num_pagina_actual=1)

        tabla = Table(title=f"Ofertas encontradas — {portal.nombre}", box=box.ROUNDED)
        tabla.add_column("#", style="dim", width=4)
        tabla.add_column("Título", style="yellow")
        tabla.add_column("URL", style="dim")

        for i, o in enumerate(ofertas, 1):
            tabla.add_row(str(i), o["titulo"][:50], o["url"])

        console.print(tabla)
        console.print(f"\n[green]Total: {len(ofertas)} ofertas[/green]")

    finally:
        try:
            if browser: browser.close()
            if p: p.stop()
        except:
            pass


# ─────────────────────────────────────────────────────────────────
#  VER POSTULACIONES
# ─────────────────────────────────────────────────────────────────

def ver_postulaciones():
    """Vista interactiva del historial de postulaciones."""
    inicializar_db()
    
    while True:
        rows = listar_postulaciones()
        # Separar activas de descartadas
        activas = [r for r in rows if r.get("estado") not in ("omitida", "no_relevante", "palabra_prohibida", "empresa_bloqueada", "falta_palabra_obligatoria")]
        descartadas = [r for r in rows if r not in activas]

        console.print(Panel(
            f"[bold cyan]📊 RESUMEN HISTÓRICO[/bold cyan]\n"
            f"  [green]✅ Enviadas/Proceso :[/green] {len(activas)}\n"
            f"  [yellow]🚫 Descartadas        :[/yellow] {len(descartadas)}\n"
            f"  [white]🌍 Total acumulado    :[/white] {len(rows)}",
            border_style="blue"
        ))

        console.print("  [1] 📋 Ver Postulaciones Activas")
        console.print("  [2] 🚫 Ver Ofertas Descartadas")
        console.print("  [3] 🗑️  Borrar TODO el historial (Activas y Descartadas)")
        console.print("  [0] 🔙 Volver al menú principal")
        
        opc = input("\n  Selecciona una opción: ").strip()
        
        if opc == "1":
            _mostrar_tabla_interactiva(activas, "Postulaciones Activas")
        elif opc == "2":
            _mostrar_tabla_interactiva(descartadas, "Ofertas Descartadas")
        elif opc == "3":
            conf = input("  [red]⚠️ ¿Estás COMPLETAMENTE SEGURO de querer borrar TODO el historial visible e invisible? [s/N]: [/red]").strip().lower()
            if conf == 's':
                from database import borrar_todas_por_estado
                estados = list(set([r.get('estado') for r in rows]))
                if estados:
                    borrar_todas_por_estado(estados)
                    console.print("  [green]✅ Todo el historial ha sido eliminado exitosamente.[/green]")
                else:
                    console.print("  [yellow]No hay nada que borrar.[/yellow]")
                import time
                time.sleep(1.5)
        elif opc == "0":
            break

def _mostrar_tabla_interactiva(rows, titulo_seccion):
    from database import borrar_oferta_por_id, borrar_todas_por_estado
    import time
    
    if not rows:
        console.print(f"[yellow]No hay registros en {titulo_seccion}.[/yellow]")
        time.sleep(2)
        return

    colores = {
        "enviada": "green",
        "saltada": "yellow",
        "error": "red",
        "error_boton": "red",
        "duplicado": "dim",
        "no_relevante": "yellow",
        "palabra_prohibida": "red",
    }

    while True:
        console.clear()
        if not rows:
            console.print(f"[yellow]No hay más registros en {titulo_seccion}.[/yellow]")
            time.sleep(2)
            break
            
        tabla = Table(title=f"📋 {titulo_seccion} ({len(rows)})", box=box.ROUNDED)
        tabla.add_column("IDX", style="dim", width=4)
        tabla.add_column("Fecha", style="dim", width=16)
        tabla.add_column("Portal", style="blue", width=12)
        tabla.add_column("Empresa", style="cyan", width=15)
        tabla.add_column("Título / Link", style="yellow", width=25)
        tabla.add_column("Estado", style="bold", width=15)
        
        for i, r in enumerate(rows, 1):
            estado = r.get("estado", "")
            color = colores.get(estado, "white")
            portal = (r.get("portal") or "legacy").upper()
            titulo = (r.get("titulo") or "")[:25]
            url = r.get("url", "")
            empresa = (r.get("empresa") or "N/A")[:15]
            
            # Hacer el título un link cliqueable si hay URL
            titulo_link = f"[link={url}]{titulo}[/link]" if url else titulo
            
            tabla.add_row(
                str(i),
                r.get("fecha", ""),
                portal,
                empresa,
                titulo_link,
                f"[{color}]{estado}[/{color}]"
            )
        
        console.print(tabla)
        console.print("\n  [idx]      Ver detalle de una oferta")
        console.print("  [del idx]  Borrar un registro (ej: 'del 1')")
        console.print("  [del all]  Borrar TODOS los registros de esta lista")
        console.print("  [0]        Volver")
        
        sel = input("\n  Selección: ").strip().lower()
        if sel == "0":
            break
        
        if sel.startswith("del "):
            cmd = sel.split(" ")[1]
            if cmd == "all":
                conf = input(f"  [red]⚠️ ¿Estás seguro de BORRAR TODOS LOS {len(rows)} REGISTROS de esta lista? [s/N]: [/red]").strip().lower()
                if conf == 's':
                    # Determinar qué estados borrar según la tabla activa
                    estados_a_borrar = list(set([r.get('estado') for r in rows]))
                    if estados_a_borrar:
                        borrar_todas_por_estado(estados_a_borrar)
                        console.print("  [green]✅ Todos los registros han sido borrados.[/green]")
                        time.sleep(1.5)
                    break
            elif cmd.isdigit() and 1 <= int(cmd) <= len(rows):
                idx = int(cmd) - 1
                registro_a_borrar = rows[idx]
                id_db = registro_a_borrar.get('id')
                if id_db:
                    borrar_oferta_por_id(id_db)
                    console.print(f"  [green]✅ Registro borrado.[/green]")
                    time.sleep(1)
                    # Remover de la lista en memoria para redibujar
                    rows.pop(idx)
                else:
                    console.print(f"  [red]❌ Error: el registro no tiene un ID válido en la base de datos.[/red]")
                    time.sleep(1.5)
        elif sel.isdigit() and 1 <= int(sel) <= len(rows):
            _ver_detalle_registro(rows[int(sel)-1])

def _ver_detalle_registro(r):
    console.print(Panel(
        f"[bold cyan]ID:[/bold cyan] {r.get('oferta_id')}\n"
        f"[bold cyan]Portal:[/bold cyan] {r.get('portal', 'N/A')}\n"
        f"[bold cyan]Título:[/bold cyan] {r.get('titulo')}\n"
        f"[bold cyan]Empresa:[/bold cyan] {r.get('empresa')}\n"
        f"[bold cyan]Fecha:[/bold cyan] {r.get('fecha')}\n"
        f"[bold cyan]Estado:[/bold cyan] {r.get('estado')}\n"
        f"[bold cyan]URL:[/bold cyan] [link={r.get('url')}]{r.get('url')}[/link]",
        title="[bold white]DETALLE DE POSTULACIÓN[/bold white]",
        border_style="green"
    ))
    
    respuestas = r.get("respuestas")
    if respuestas:
        console.print(Panel(
            f"[italic white]{respuestas}[/italic white]",
            title="[bold magenta]Respuestas de la IA[/bold magenta]",
            border_style="magenta"
        ))
    
    input("\n  Presiona Enter para volver a la lista...")


# ─────────────────────────────────────────────────────────────────
#  VER DESCARTADAS / BANEADAS
# ─────────────────────────────────────────────────────────────────

def ver_omitidas():
    inicializar_db()
    rows = listar_omitidas()

    if not rows:
        console.print("[yellow]No hay ofertas descartadas registradas aún.[/yellow]")
        return

    etiquetas = {
        "no_relevante": ("🤖 No relevante", "yellow"),
        "palabra_prohibida": ("🚫 Palabra bloqueada", "red"),
        "omitida": ("⏭ Omitida", "dim"),
        "experiencia_alta": ("👴 Mucha Exp", "yellow"),
        "empresa_bloqueada": ("🏢 Empresa Bloqueada", "red"),
        "falta_palabra_obligatoria": ("⚠️ Falta Keyword", "red")
    }

    tabla = Table(title=f"Ofertas Descartadas ({len(rows)} total)", box=box.ROUNDED)
    tabla.add_column("Fecha", style="dim", width=16)
    tabla.add_column("Empresa", style="cyan", width=15)
    tabla.add_column("Título / Link", style="yellow", width=25)
    tabla.add_column("Motivo", style="bold")

    for r in rows:
        estado = r.get("estado", "")
        etiqueta, color = etiquetas.get(estado, (estado, "white"))
        titulo = (r.get("titulo") or "")[:25]
        url = r.get("url", "")
        empresa = (r.get("empresa") or "N/A")[:15]
        
        titulo_link = f"[link={url}]{titulo}[/link]" if url else titulo

        tabla.add_row(
            r.get("fecha", ""),
            empresa,
            titulo_link,
            f"[{color}]{etiqueta}[/{color}]"
        )

    console.print(tabla)
    input("\n  Presiona Enter para volver a la lista...")


def menu_gestion_filtros_rechazo():
    """Menú completo para gestionar todos los filtros de descarte automático."""
    while True:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        # Cargamos valores actuales
        palabras = FILTROS.get("palabras_prohibidas", [])
        empresas = FILTROS.get("empresas_prohibidas", [])
        obligatorias = FILTROS.get("palabras_obligatorias", [])
        solo_remoto = FILTROS.get("solo_remoto", False)
        renta_estricta = FILTROS.get("renta_minima_estricta", False)

        region = FILTROS.get("region", "Santiago, Chile")
        ciudad = FILTROS.get("ciudad", "Santiago")

        console.print(Panel(
            f"  [bold cyan]1. Palabras Prohibidas:[/bold cyan] {', '.join(palabras) if palabras else '[dim]Ninguna[/dim]'}\n"
            f"  [bold cyan]2. Empresas Ignoradas:[/bold cyan] {', '.join(empresas) if empresas else '[dim]Ninguna[/dim]'}\n"
            f"  [bold cyan]3. Palabras Obligatorias:[/bold cyan] {', '.join(obligatorias) if obligatorias else '[dim]Ninguna[/dim]'}\n"
            f"  [bold cyan]4. 📍 Región de Búsqueda (Duoc):[/bold cyan] [green]{region}[/green]\n"
            f"  [bold cyan]5. 🏙️  Ciudad de Búsqueda (CT):[/bold cyan]     [green]{ciudad}[/green]",
            title="🎯 GESTIÓN DE FILTROS DE BÚSQUEDA",
            subtitle="Personaliza tus criterios de búsqueda y rechazo",
            box=box.DOUBLE
        ))
        
        console.print("  [1] 🚫 Gestionar Palabras Prohibidas")
        console.print("  [2] 🏢 Gestionar Lista Negra de Empresas")
        console.print("  [3] ✅ Gestionar Palabras Obligatorias")
        console.print("  [4] 📍 Cambiar Región de Búsqueda")
        console.print("  [5] 🏙️  Cambiar Ciudad de Búsqueda")
        console.print("  [0] 🔙 Volver al menú principal")
        
        opc = input("\n  Selecciona una opción: ").strip()
        
        if opc == "1":
            menu_lista_simple("palabras_prohibidas", "Palabra Prohibida")
        elif opc == "2":
            menu_lista_simple("empresas_prohibidas", "Empresa a Bloquear")
        elif opc == "3":
            menu_lista_simple("palabras_obligatorias", "Palabra Obligatoria (debe estar en el título)")
        elif opc == "4":
            menu_cambiar_region()
        elif opc == "5":
            menu_cambiar_ciudad()
        elif opc == "0":
            break

def menu_cambiar_region():
    """Permite al usuario cambiar la región de búsqueda."""
    while True:
        actual = FILTROS.get("region", "Santiago, Chile")
        console.print(f"\n  [bold cyan]📍 Configuración de Región[/bold cyan]")
        console.print(f"  Región actual: [green]{actual}[/green]")
        console.print(f"  [1] 🌏 Cambiar Región")
        console.print(f"  [0] 🔙 Volver")
        
        opc = input("\n  Selecciona: ").strip()
        if opc == "1":
            nueva = input("  Ingresa la nueva región (ej: Región Metropolitana): ").strip()
            if nueva:
                FILTROS["region"] = nueva
                guardar_filtros(FILTROS)
                console.print(f"  [green]✅ Región actualizada a: {nueva}[/green]")
            break
        elif opc == "0":
            break

def menu_cambiar_ciudad():
    """Permite al usuario cambiar la ciudad de búsqueda."""
    while True:
        actual = FILTROS.get("ciudad", "Santiago")
        console.print(f"\n  [bold cyan]🏙️ Configuración de Ciudad[/bold cyan]")
        console.print(f"  Ciudad actual: [green]{actual}[/green]")
        console.print(f"  [1] 🏙️ Cambiar Ciudad")
        console.print(f"  [0] 🔙 Volver")
        
        opc = input("\n  Selecciona: ").strip()
        if opc == "1":
            nueva = input("  Ingresa la nueva ciudad (ej: Temuco): ").strip()
            if nueva:
                FILTROS["ciudad"] = nueva
                guardar_filtros(FILTROS)
                console.print(f"  [green]✅ Ciudad actualizada a: {nueva}[/green]")
            break
        elif opc == "0":
            break

def menu_lista_simple(key_filtro, nombre_item):
    """Sub-menú genérico para agregar/quitar elementos de una lista de filtros."""
    while True:
        lista = FILTROS.get(key_filtro, [])
        console.print(f"\n  [bold yellow]--- Gestión de {key_filtro.replace('_', ' ').title()} ---[/bold yellow]")
        console.print(f"  Items actuales: {', '.join(lista) if lista else '[dim]Vacío[/dim]'}")
        console.print(f"  [1] ➕ Agregar {nombre_item}")
        console.print(f"  [2] ➖ Quitar {nombre_item}")
        console.print("  [0] 🔙 Volver")
        
        opc = input(f"  Opción ({key_filtro}): ").strip()
        if opc == "1":
            nuevo = input(f"  Ingresa {nombre_item}: ").strip().lower()
            if nuevo and nuevo not in lista:
                lista.append(nuevo)
                FILTROS[key_filtro] = lista
                guardar_filtros(FILTROS)
                console.print(f"  [green]✔ '{nuevo}' agregado.[/green]")
        elif opc == "2":
            if not lista: continue
            quitar = input(f"  Ingresa {nombre_item} a eliminar: ").strip().lower()
            if quitar in lista:
                lista.remove(quitar)
                FILTROS[key_filtro] = lista
                guardar_filtros(FILTROS)
                console.print(f"  [green]✔ '{quitar}' eliminado.[/green]")
        elif opc == "0":
            break

# ─────────────────────────────────────────────────────────────────
def menu_gestion_experiencia(perfil):
    """Menú CRUD para gestionar experiencias laborales."""
    if "experiencia_laboral" not in perfil:
        perfil["experiencia_laboral"] = []

    while True:
        exp_list = perfil["experiencia_laboral"]
        console.print(Panel.fit(
            "[bold white]🏢 GESTIÓN DE EXPERIENCIA LABORAL[/bold white]\n"
            "[dim]Describe tus trabajos anteriores para que la IA los use en las postulaciones.[/dim]",
            border_style="blue"
        ))

        if not exp_list:
            console.print("  [yellow]No tienes experiencias registradas.[/yellow]")
        else:
            for i, exp in enumerate(exp_list, 1):
                console.print(f"  {i}. [bold cyan]{exp.get('empresa', 'Empresa')}[/bold cyan] - {exp.get('cargo', 'Cargo')} ({exp.get('fecha', 'Fecha no especificada')})")
                console.print(f"     [dim]{exp.get('descripcion', '')[:60]}...[/dim]")
        
        console.print("\n  [A] ➕ Agregar Experiencia")
        console.print("  [B] 🗑️  Borrar Experiencia")
        console.print("  [0] 🔙 Volver")

        opc = input("\n  Selecciona una opción: ").strip().upper()

        if opc == "0":
            break
        elif opc == "A":
            empresa = input("  1. Nombre de la empresa: ").strip()
            cargo = input("  2. Cargo desempeñado: ").strip()
            fecha = input("  3. Periodo (ej: 2021-2023 o 'Actual'): ").strip()
            desc = input("  4. Breve descripción de tus tareas: ").strip()
            
            if empresa and cargo:
                perfil["experiencia_laboral"].append({
                    "empresa": empresa,
                    "cargo": cargo,
                    "fecha": fecha,
                    "descripcion": desc
                })
                guardar_perfil(perfil)
                console.print("[green]✅ Experiencia agregada.[/green]")
        elif opc == "B":
            if not exp_list: continue
            idx = input("  Número a borrar: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(exp_list):
                eliminado = perfil["experiencia_laboral"].pop(int(idx)-1)
                guardar_perfil(perfil)
                console.print(f"[red]🗑️ Eliminado: {eliminado['empresa']}[/red]")

def menu_perfil_usuario():
    """Menú para gestionar la identidad y datos del candidato."""
    while True:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        import config
        perfil = cargar_perfil()
        cargo_actual = FILTROS.get("carrera", "No definido")
        
        pref = perfil.get('preferencias', {})
        renta = pref.get('renta_esperada', 'No definida')
        disp = pref.get('disponibilidad', 'No definida')
        
        console.print(Panel(
            f"[bold cyan]👤 PERFIL DE USUARIO[/bold cyan]\n"
            f"  [white]Propósito:[/white] Postular como [bold blue]{cargo_actual}[/bold blue]\n"
            f"  [white]Identidad:[/white] [bold blue]{perfil.get('nombre_completo', 'Desconocido')}[/bold blue]\n"
            f"  [white]Ubicación:[/white] [bold blue]{perfil.get('ubicacion', 'No definida')}[/bold blue]\n"
            f"  [white]Expectativa:[/white] [bold green]${renta}[/bold green] | [bold yellow]{disp}[/bold yellow]",
            border_style="cyan"
        ))

        console.print("  [1] 👤 Editar Datos Básicos (Nombre, RUT, Email, Educación, Renta)")
        console.print("  [2] 🎯 Cargo a Buscar")
        console.print(f"  [3] 📄 Gestionar CV ([dim]{os.path.basename(config.CV_PATH) if config.CV_PATH and os.path.exists(config.CV_PATH) else 'No configurado'}[/dim])")
        console.print("  [4] 🏢 Gestionar Experiencia Laboral")
        console.print("  [0] 🔙 Volver al centro de mando\n")

        opc = input("  ¿Qué quieres modificar? [0-4]: ").strip()

        if opc == "1":
            menu_editar_perfil_basico(perfil)
        elif opc == "2":
            from constantes import DUOC_CARRERAS
            opciones_carrera = dict(DUOC_CARRERAS)
            opciones_carrera["✏️  Escribir manualmente"] = "MANUAL"
            nuevo_cargo = menu_seleccionar_opcion(opciones_carrera, "🎯 Cargo a Buscar")
            if nuevo_cargo == "✏️  Escribir manualmente" or nuevo_cargo == "MANUAL":
                nuevo_cargo = None
            if not nuevo_cargo:
                console.print("\n  [bold cyan]✏️  Escribe el cargo tal como lo buscarías en Google:[/bold cyan]")
                console.print("  [dim]ej: \"Desarrollador Full Stack\", \"Soporte TI\", \"Analista de Datos\"[/dim]")
                nuevo_cargo = input("\n  > ").strip()
            if nuevo_cargo:
                FILTROS["carrera"] = nuevo_cargo
                perfil["cargo_objetivo"] = nuevo_cargo
                guardar_filtros(FILTROS)
                guardar_perfil(perfil)
                console.print(f"\n  [green]✅ Cargo actualizado: [bold]{nuevo_cargo}[/bold][/green]\n")
        elif opc == "3":
            menu_gestion_cv()
        elif opc == "4":
            menu_gestion_experiencia(perfil)
        elif opc == "0":
            break
        
        if opc in ["1", "2", "3", "4"]:
            guardar_perfil(perfil)
            console.print("[green]✅  Cambios aplicados.[/green]\n")

def menu_editar_perfil_basico(perfil):
    """Sub-menú para editar datos básicos agrupados."""
    while True:
        console.print(Panel.fit(
            "[bold white]👤 EDICIÓN DE PERFIL Y DATOS[/bold white]",
            border_style="white"
        ))
        console.print(f"  [1] Nombre       : {perfil.get('nombre_completo')}")
        console.print(f"  [2] RUT          : {perfil.get('rut') or 'No definido'}")
        console.print(f"  [3] Email        : {perfil.get('email')}")
        console.print(f"  [4] Teléfono     : {perfil.get('telefono')}")
        # Obtener educación de forma segura
        edu_list = perfil.get('educacion', [])
        edu_titulo = edu_list[0].get('titulo', 'N/A') if edu_list else 'N/A'
        console.print(f"  [5] Educación    : {edu_titulo}")
        console.print(f"  [6] Ubicación    : {perfil.get('ubicacion')}")
        
        pref = perfil.get('preferencias', {})
        console.print(f"  [7] Preferencias : ${pref.get('renta_esperada', 'N/A')} | {pref.get('disponibilidad', 'N/A')}")
        console.print("  [0] 🔙 Volver al menú anterior")
        
        sub = input("\n  ¿Qué dato quieres cambiar? [0-7]: ").strip()
        
        if sub == "1":
            perfil["nombre_completo"] = input("  Nuevo Nombre: ").strip() or perfil["nombre_completo"]
        elif sub == "2":
            perfil["rut"] = input("  Nuevo RUT: ").strip() or perfil.get("rut", "")
        elif sub == "3":
            e = input("  Nuevo Email: ").strip()
            if es_email_valido(e): perfil["email"] = e
        elif sub == "4":
            t = input("  Nuevo Teléfono: ").strip()
            if es_telefono_valido(t): perfil["telefono"] = t
        elif sub == "5":
            edu = input("  Nuevo Título/Educación: ").strip()
            if edu: perfil["educacion"] = [{"titulo": edu, "institucion": "Por definir", "estado": "Titulado"}]
        elif sub == "6":
            from constantes import DUOC_REGIONES, DUOC_COMUNAS
            console.print("\n  [bold cyan]Actualizando Ubicación...[/bold cyan]")
            time.sleep(1)
            opciones_reg = {"Cualquiera": ""}
            opciones_reg.update(DUOC_REGIONES)
            reg = menu_seleccionar_opcion(opciones_reg, "Nueva Región", "region")
            
            opciones_com = {"Cualquiera": ""}
            opciones_com.update(DUOC_COMUNAS)
            com = menu_seleccionar_opcion(opciones_com, "Nueva Comuna", "comuna")
            
            ubi_final = com if com and com != "Cualquiera" else reg
            if com and com != "Cualquiera" and reg and reg != "Cualquiera":
                ubi_final = f"{com}, {reg}"
            elif reg and reg != "Cualquiera":
                ubi_final = reg
                
            if ubi_final:
                perfil["ubicacion"] = ubi_final
        elif sub == "7":
            if "preferencias" not in perfil: perfil["preferencias"] = {}
            perfil["preferencias"]["renta_esperada"] = input(f"  Renta ({perfil['preferencias'].get('renta_esperada')}): ").strip() or perfil['preferencias'].get('renta_esperada')
            perfil["preferencias"]["disponibilidad"] = input(f"  Dispo ({perfil['preferencias'].get('disponibilidad')}): ").strip() or perfil['preferencias'].get('disponibilidad')
        elif sub == "0":
            break
        
        guardar_perfil(perfil)
        console.print("[green]✅  Dato actualizado.[/green]\n")

_FAQS_PREDETERMINADAS = [
    {"pregunta": "¿Por qué deberíamos contratarte?",                        "respuesta": ""},
    {"pregunta": "¿Cuál es tu mayor fortaleza?",                            "respuesta": ""},
    {"pregunta": "¿Cuál es tu mayor debilidad?",                            "respuesta": ""},
    {"pregunta": "¿Dónde te ves en 5 años?",                               "respuesta": ""},
    {"pregunta": "¿Por qué quieres trabajar en esta empresa?",              "respuesta": ""},
    {"pregunta": "¿Tienes experiencia trabajando en equipo?",               "respuesta": ""},
    {"pregunta": "¿Cómo manejas situaciones de presión o alta carga?",     "respuesta": ""},
    {"pregunta": "¿Cuál es tu expectativa de renta?",                       "respuesta": ""},
    {"pregunta": "¿Por qué dejaste tu trabajo anterior?",                   "respuesta": ""},
    {"pregunta": "¿Tienes disponibilidad inmediata?",                       "respuesta": ""},
    {"pregunta": "¿Qué sabes de esta empresa o industria?",                 "respuesta": ""},
    {"pregunta": "¿Cómo describes tu estilo de trabajo?",                   "respuesta": ""},
    {"pregunta": "¿Has liderado equipos o proyectos anteriormente?",        "respuesta": ""},
    {"pregunta": "¿Qué habilidades técnicas manejas?",                      "respuesta": ""},
    {"pregunta": "¿Por qué cambiaste de carrera o área profesional?",       "respuesta": ""},
]


def _cargar_faqs_predeterminadas(perfil):
    """Carga las 15 FAQs predeterminadas (sin respuesta) evitando duplicados."""
    existentes = {item["pregunta"] for item in perfil.get("preguntas_frecuentes", [])}
    nuevas = [faq for faq in _FAQS_PREDETERMINADAS if faq["pregunta"] not in existentes]
    if not nuevas:
        console.print("  [yellow]⚠️  Todas las FAQs predeterminadas ya están cargadas.[/yellow]")
        time.sleep(1.5)
        return
    perfil.setdefault("preguntas_frecuentes", []).extend(nuevas)
    guardar_perfil(perfil)
    console.print(f"  [bold green]✅ {len(nuevas)} FAQs cargadas — ahora escribe tu respuesta en cada una.[/bold green]")
    time.sleep(2)


def menu_preguntas_frecuentes(perfil):
    """Menú para gestionar pares de Pregunta/Respuesta para entrenar a la IA."""
    if "preguntas_frecuentes" not in perfil:
        perfil["preguntas_frecuentes"] = []

    # Auto-cargar FAQs la primera vez que la lista está vacía
    if not perfil["preguntas_frecuentes"]:
        console.print("  [dim]💡 Lista vacía — cargando 15 preguntas frecuentes...[/dim]")
        _cargar_faqs_predeterminadas(perfil)

    while True:
        console.clear()
        faqs = perfil["preguntas_frecuentes"]

        console.print(Panel.fit(
            "[bold magenta]❓ FAQ / ENTRENAMIENTO DE RESPUESTAS[/bold magenta]\n"
            "[dim]Escribe el número de una pregunta para ver y editar tu respuesta.[/dim]",
            border_style="magenta"
        ))
        console.print()

        if not faqs:
            console.print("  [yellow]No hay preguntas registradas.[/yellow]\n")
        else:
            t = Table(box=box.SIMPLE_HEAVY, show_header=True,
                      header_style="bold white on dark_magenta", padding=(0, 1))
            t.add_column("N°", style="bold yellow", justify="right", width=3)
            t.add_column("Pregunta", style="bold cyan", width=48)
            t.add_column("Estado", style="dim", width=12)

            for i, item in enumerate(faqs, 1):
                tiene_resp = bool(item.get("respuesta", "").strip())
                estado = "[bold green]✅ Respondida[/bold green]" if tiene_resp else "[bold red]❌ Sin respuesta[/bold red]"
                t.add_row(str(i), item["pregunta"], estado)

            console.print(t)
            console.print()

        console.print("  [dim]💡 Escribe el [bold yellow]número[/bold yellow] de una pregunta para ver y escribir tu respuesta[/dim]")
        console.print()
        console.print("  [A] ➕ Agregar nueva pregunta")
        console.print("  [B] 🗑️  Eliminar una pregunta")
        console.print("  [C] 🔄 Recargar las 15 preguntas predeterminadas")
        console.print("  [0] 🔙 Volver al menú principal")
        console.print()

        opc = input("  Opción o número de pregunta: ").strip()

        if not opc:
            continue
        elif opc == "0":
            break
        elif opc.upper() == "A":
            console.print()
            q = input("  Escribe la nueva pregunta: ").strip()
            if q:
                a = input("  Escribe tu respuesta: ").strip()
                perfil["preguntas_frecuentes"].append({"pregunta": q, "respuesta": a})
                guardar_perfil(perfil)
                console.print("[green]✅ Pregunta agregada.[/green]")
                time.sleep(1)
        elif opc.upper() == "B":
            if not faqs:
                console.print("[yellow]No hay preguntas para eliminar.[/yellow]")
                time.sleep(1)
                continue
            console.print()
            num = input("  ¿Cuál número de pregunta deseas eliminar? (ej: 3): ").strip()
            if num.isdigit() and 1 <= int(num) <= len(faqs):
                eliminado = perfil["preguntas_frecuentes"].pop(int(num)-1)
                guardar_perfil(perfil)
                console.print(f"[red]🗑️ Eliminada: {eliminado['pregunta']}[/red]")
                time.sleep(1.5)
            else:
                console.print("[red]❌ Número no válido.[/red]")
                time.sleep(1)
        elif opc.upper() == "C":
            _cargar_faqs_predeterminadas(perfil)
        elif opc.isdigit():
            idx = int(opc) - 1
            if 0 <= idx < len(faqs):
                item = faqs[idx]
                console.clear()
                console.print(Panel(
                    f"[bold cyan]Pregunta N° {idx+1} de {len(faqs)}[/bold cyan]\n\n"
                    f"[bold white]{item['pregunta']}[/bold white]\n\n"
                    f"[bold green]Tu respuesta actual:[/bold green]\n"
                    + (f"[italic white]{item['respuesta']}[/italic white]" if item.get('respuesta') else "[dim italic]Sin respuesta — escribe la tuya abajo.[/dim italic]"),
                    border_style="magenta", padding=(1, 2)
                ))
                console.print()
                console.print("  [dim]Escribe tu respuesta. Presiona Enter sin escribir nada para dejar igual.[/dim]")
                nueva_resp = input("  Tu respuesta: ").strip()
                if nueva_resp:
                    perfil["preguntas_frecuentes"][idx]["respuesta"] = nueva_resp
                    guardar_perfil(perfil)
                    console.print("[green]✅ Respuesta guardada correctamente.[/green]")
                    time.sleep(1.2)
            else:
                console.print(f"[red]❌ El número debe estar entre 1 y {len(faqs)}.[/red]")
                time.sleep(1)
        else:
            console.print("[dim]No reconocí esa opción. Prueba con un número, A, B, C o 0.[/dim]")
            time.sleep(1)


def menu_agregar_preguntas(perfil):
    """[5] Solo permite agregar nuevas preguntas o eliminar — sin mostrar la lista completa."""
    if "preguntas_frecuentes" not in perfil:
        perfil["preguntas_frecuentes"] = []
    # Auto-cargar si está vacío
    if not perfil["preguntas_frecuentes"]:
        console.print("  [dim]💡 Lista vacía — cargando 15 preguntas base...[/dim]")
        _cargar_faqs_predeterminadas(perfil)

    while True:
        console.clear()
        total = len(perfil["preguntas_frecuentes"])
        resp = sum(1 for f in perfil["preguntas_frecuentes"] if f.get("respuesta", "").strip())

        console.print(Panel.fit(
            "[bold magenta]✏️  AGREGAR PREGUNTA DE ENTREVISTA[/bold magenta]\n"
            "[dim]Agrega tus respuestas a las preguntas que más te hacen las empresas.[/dim]",
            border_style="magenta"
        ))
        console.print(f"  [dim]Tienes [bold yellow]{total}[/bold yellow] preguntas — "
                      f"[bold green]{resp}[/bold green] respondidas / "
                      f"[bold red]{total - resp}[/bold red] sin respuesta.[/dim]\n")
        console.print("  [1] ➕ Agregar nueva pregunta")
        console.print("  [2] 🗑️  Eliminar una pregunta")
        console.print("  [3] 🔄 Recargar las 15 preguntas predeterminadas")
        console.print("  [0] 🔙 Volver")
        console.print()

        opc = input("  Opción: ").strip()

        if opc == "0":
            break
        elif opc == "1":
            console.print()
            q = input("  ¿Cuál es la pregunta? (ej: ¿Tienes experiencia con Python?): ").strip()
            if q:
                a = input("  ¿Cuál es tu respuesta?: ").strip()
                perfil["preguntas_frecuentes"].append({"pregunta": q, "respuesta": a})
                guardar_perfil(perfil)
                console.print("[green]✅ Pregunta agregada.[/green]")
                time.sleep(1.2)
        elif opc == "2":
            faqs = perfil["preguntas_frecuentes"]
            if not faqs:
                console.print("[yellow]No hay preguntas para eliminar.[/yellow]")
                time.sleep(1)
                continue
            console.print()
            console.print("  [dim]Preguntas disponibles:[/dim]")
            for i, f in enumerate(faqs, 1):
                console.print(f"  {i}. {f['pregunta']}")
            console.print()
            num = input("  Número a eliminar (0 = cancelar): ").strip()
            if num == "0":
                continue
            if num.isdigit() and 1 <= int(num) <= len(faqs):
                eliminado = perfil["preguntas_frecuentes"].pop(int(num) - 1)
                guardar_perfil(perfil)
                console.print(f"[red]🗑️ Eliminada: {eliminado['pregunta']}[/red]")
                time.sleep(1.5)
            else:
                console.print("[red]❌ Número no válido.[/red]")
                time.sleep(1)
        elif opc == "3":
            _cargar_faqs_predeterminadas(perfil)
        else:
            console.print("[dim]Opción no reconocida.[/dim]")
            time.sleep(0.8)


def menu_ver_preguntas(perfil):
    """[6] Muestra la lista completa de preguntas — permite ver la respuesta completa, editarla y eliminar."""
    if "preguntas_frecuentes" not in perfil:
        perfil["preguntas_frecuentes"] = []
    if not perfil["preguntas_frecuentes"]:
        console.print("  [yellow]No hay preguntas registradas. Ve a [5] para agregar.[/yellow]")
        time.sleep(2)
        return

    while True:
        console.clear()
        faqs = perfil["preguntas_frecuentes"]

        console.print(Panel.fit(
            "[bold cyan]📋 MIS PREGUNTAS DE ENTREVISTA[/bold cyan]\n"
            "[dim]Selecciona un número para ver la respuesta completa y editarla.[/dim]",
            border_style="cyan"
        ))
        console.print()

        t = Table(box=box.SIMPLE_HEAVY, show_header=True,
                  header_style="bold white on dark_cyan", padding=(0, 1))
        t.add_column("N°", style="bold yellow", justify="right", width=3)
        t.add_column("Pregunta", style="bold white", width=50)
        t.add_column("Estado", width=14)

        for i, item in enumerate(faqs, 1):
            tiene_resp = bool(item.get("respuesta", "").strip())
            estado = "[bold green]✅ Respondida[/bold green]" if tiene_resp else "[bold red]❌ Sin respuesta[/bold red]"
            t.add_row(str(i), item["pregunta"], estado)

        console.print(t)
        console.print()
        console.print("  [dim]Escribe el [bold yellow]número[/bold yellow] para ver/editar una respuesta │ "
                      "[bold red]D Nº[/bold red] para borrar (ej: D 3) │ "
                      "[bold white]0[/bold white] volver[/dim]")
        console.print()

        opc = input("  Opción: ").strip()

        if not opc or opc == "0":
            break
        elif opc.upper().startswith("D"):
            partes = opc.split()
            if len(partes) == 2 and partes[1].isdigit():
                idx = int(partes[1]) - 1
                if 0 <= idx < len(faqs):
                    eliminado = perfil["preguntas_frecuentes"].pop(idx)
                    guardar_perfil(perfil)
                    console.print(f"[red]🗑️ Eliminada: {eliminado['pregunta']}[/red]")
                    time.sleep(1.5)
                    if not perfil["preguntas_frecuentes"]:
                        break
                else:
                    console.print("[red]❌ Número fuera de rango.[/red]"); time.sleep(1)
            else:
                console.print("[dim]Usa el formato: D 3 (para borrar la pregunta 3)[/dim]"); time.sleep(1.2)
        elif opc.isdigit():
            idx = int(opc) - 1
            if 0 <= idx < len(faqs):
                item = faqs[idx]
                console.clear()
                console.print(Panel(
                    f"[bold cyan]Pregunta N° {idx+1} de {len(faqs)}:[/bold cyan]\n\n"
                    f"[bold white]{item['pregunta']}[/bold white]\n\n"
                    f"[bold green]Tu respuesta actual:[/bold green]\n"
                    + (f"[italic white]{item['respuesta']}[/italic white]"
                       if item.get('respuesta') else "[dim italic]Sin respuesta — escribe la tuya abajo.[/dim italic]"),
                    border_style="cyan", padding=(1, 2)
                ))
                console.print()
                console.print("  [dim]Escribe tu respuesta. Enter en blanco = dejar igual.[/dim]")
                nueva = input("  Tu respuesta: ").strip()
                if nueva:
                    perfil["preguntas_frecuentes"][idx]["respuesta"] = nueva
                    guardar_perfil(perfil)
                    console.print("[green]✅ Guardada.[/green]")
                    time.sleep(1.2)
            else:
                console.print(f"[red]❌ Número entre 1 y {len(faqs)}.[/red]"); time.sleep(1)
        else:
            console.print("[dim]Opción no reconocida.[/dim]"); time.sleep(0.8)



def menu_gestion_cv():
    """Menú para gestionar el CV: subir desde escritorio, cambiar ruta o eliminar."""
    from config import actualizar_variable_env
    
    while True:
        import config
        importlib.reload(config)
        current_cv = config.CV_PATH
        existe = os.path.exists(current_cv) if current_cv else False
        nombre_cv = os.path.basename(current_cv) if current_cv else None

        estado_txt = (
            f"[bold green]✅ {nombre_cv}[/bold green]"
            if existe
            else (
                f"[bold yellow]⚠️  Ruta configurada pero archivo no encontrado:[/bold yellow]\n   [dim]{current_cv}[/dim]"
                if current_cv
                else "[bold red]❌ Ningún CV configurado[/bold red]"
            )
        )

        console.print(Panel(
            "[bold cyan]📄 GESTIÓN DE CURRÍCULUM VITAE (CV)[/bold cyan]\n\n"
            f"  Estado: {estado_txt}\n\n"
            "[dim]El CV se adjunta automáticamente al postular en portales que lo soliciten.[/dim]",
            border_style="cyan"
        ))

        console.print("  [1] 📂 Subir / Cambiar CV  [dim](abre explorador de archivos)[/dim]")
        console.print("  [2] ✏️   Escribir ruta manualmente")
        if current_cv:
            console.print("  [3] 🗑️   Eliminar CV configurado")
        console.print("  [0] 🔙 Volver")

        opc = input("\n  Selecciona una opción: ").strip()

        if opc == "1":
            console.print("\n  [dim]Abriendo explorador de archivos...[/dim]")
            nueva_ruta = seleccionar_archivo_pdf()
            if not nueva_ruta:
                console.print("  [yellow]Selección cancelada.[/yellow]")
                time.sleep(1)
                continue
            actualizar_variable_env("CV_PATH", nueva_ruta)
            console.print(f"  [green]✅ CV actualizado: [bold]{os.path.basename(nueva_ruta)}[/bold][/green]")
            time.sleep(1.5)

        elif opc == "2":
            nueva_ruta = input("  Introduce la ruta completa de tu CV (.pdf): ").strip().replace('"', '').replace("'", "")
            if not nueva_ruta:
                continue
            if not nueva_ruta.lower().endswith(".pdf"):
                console.print("  [red]❌ El archivo debe ser un PDF.[/red]")
                time.sleep(1.5)
                continue
            if not os.path.isabs(nueva_ruta):
                nueva_ruta = os.path.abspath(nueva_ruta)
            if os.path.exists(nueva_ruta):
                actualizar_variable_env("CV_PATH", nueva_ruta)
                console.print(f"  [green]✅ CV actualizado: [bold]{os.path.basename(nueva_ruta)}[/bold][/green]")
            else:
                console.print(f"  [yellow]⚠️ Archivo no encontrado, pero se guardará la ruta igualmente.[/yellow]")
                actualizar_variable_env("CV_PATH", nueva_ruta)
            time.sleep(1.5)

        elif opc == "3" and current_cv:
            confirmar = input("  ¿Seguro que quieres eliminar el CV configurado? [s/N]: ").strip().lower()
            if confirmar in ("s", "si", "sí"):
                actualizar_variable_env("CV_PATH", "")
                console.print("  [green]✅ CV eliminado correctamente.[/green]")
                time.sleep(1.5)

        elif opc == "0":
            break
        

def menu_base_conocimientos(perfil):
    if "base_conocimientos" not in perfil:
        perfil["base_conocimientos"] = []

    while True:
        console.print(Panel.fit(
            "[bold cyan]🧠 Base de Conocimientos Estructurada[/bold cyan]\n"
            "[dim]Define tus habilidades con años y nivel para respuestas precisas.[/dim]",
            border_style="cyan"
        ))
        
        kb = perfil["base_conocimientos"]
        if not kb:
            console.print("  [yellow]No tienes conocimientos guardados aún.[/yellow]\n")
        else:
            table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
            table.add_column("#", style="dim", width=3)
            table.add_column("Conocimiento", style="cyan")
            table.add_column("Años", justify="center")
            table.add_column("Nivel", style="green")
            
            for i, item in enumerate(kb, 1):
                table.add_row(
                    str(i), 
                    item.get('conocimiento', item.get('pregunta', 'N/A')), 
                    str(item.get('anos', item.get('respuesta', '0'))), 
                    item.get('nivel', 'No especificado')
                )
            console.print(table)
            console.print()

        console.print("  [A] ➕ Agregar Conocimiento")
        console.print("  [B] 🗑️  Borrar uno")
        console.print("  [0] 🔙 Volver")
        
        opc = input("\n  Opción: ").strip().upper()
        
        if opc == "A":
            conoc = input("  1. ¿Qué conocimiento/herramienta? (ej: Python): ").strip()
            if not conoc: continue
            
            anos = input("  2. ¿Cuántos años de experiencia? (ej: 2): ").strip()
            if not anos: anos = "0"
            
            console.print("  3. ¿Qué nivel manejas?")
            console.print("     [1] Nulo / Básico inicial")
            console.print("     [2] Básico")
            console.print("     [3] Intermedio")
            console.print("     [4] Avanzado / Experto")
            lvl_opc = input("     Selecciona [1-4]: ").strip()
            
            niveles = {"1": "Nulo/Básico inicial", "2": "Básico", "3": "Intermedio", "4": "Avanzado/Experto"}
            nivel = niveles.get(lvl_opc, "Básico")
            
            perfil["base_conocimientos"].append({
                "conocimiento": conoc,
                "anos": anos,
                "nivel": nivel
            })
            from config import guardar_perfil
            guardar_perfil(perfil)
            console.print(f"[green]✅ '{conoc}' guardado correctamente.[/green]")
            
        elif opc == "B":
            if not kb: continue
            idx = input("  ¿Qué número deseas borrar? (Enter para cancelar): ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(kb):
                eliminado = perfil["base_conocimientos"].pop(int(idx)-1)
                from config import guardar_perfil
                guardar_perfil(perfil)
                console.print(f"[red]🗑️ Eliminado: {eliminado.get('conocimiento', eliminado.get('pregunta'))}[/red]")
        elif opc == "0":
            break


def menu_configuracion_credenciales():
    """Menú para configurar correos y contraseñas de diversos portales."""
    from config import (
        DUOC_EMAIL, DUOC_PASSWORD,
        CHILETRABAJOS_EMAIL, CHILETRABAJOS_PASSWORD,
        LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
        GETONBOARD_EMAIL, GETONBOARD_PASSWORD,
        GROQ_API_KEY
    )
    
    def mask(s):
        if not s: return "[red]No configurado[/red]"
        if len(s) <= 4: return "*" * len(s)
        return s[:2] + "*" * (len(s)-4) + s[-2:]

    while True:
        # Recargar valores cada vez para mostrar cambios
        import config
        import importlib
        importlib.reload(config)
        from config import (
            DUOC_EMAIL, DUOC_PASSWORD,
            CHILETRABAJOS_EMAIL, CHILETRABAJOS_PASSWORD,
            LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
            GETONBOARD_EMAIL, GETONBOARD_PASSWORD,
            GROQ_API_KEY
        )

        console.print(Panel.fit(
            "[bold cyan]🔑 CONFIGURACIÓN DE ACCESOS Y CREDENCIALES[/bold cyan]\n"
            "[dim]Configura tus cuentas para que el bot pueda iniciar sesión por ti.[/dim]\n"
            "\n[bold magenta]💡 Groq API Key:[/bold magenta] [link=https://console.groq.com/keys]https://console.groq.com/keys[/link]",
            border_style="cyan"
        ))

        tabla = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        tabla.add_column("#", style="dim", width=3)
        tabla.add_column("Portal / Servicio", style="cyan", width=25)
        tabla.add_column("Email / Usuario", style="white")
        tabla.add_column("Contraseña", style="white")

        tabla.add_row("1", "🎓 DuocLaboral", DUOC_EMAIL or "[red]-[/red]", mask(DUOC_PASSWORD))
        tabla.add_row("2", "💼 ChileTrabajos", CHILETRABAJOS_EMAIL or "[red]-[/red]", mask(CHILETRABAJOS_PASSWORD))
        tabla.add_row("3", "🔗 LinkedIn", LINKEDIN_EMAIL or "[red]-[/red]", mask(LINKEDIN_PASSWORD))
        tabla.add_row("4", "🚀 Get on Board", GETONBOARD_EMAIL or "[red]-[/red]", mask(GETONBOARD_PASSWORD))
        tabla.add_row("5", "🤖 Groq API Key", "API Key", mask(GROQ_API_KEY))

        console.print(tabla)
        console.print("\n  [1-5] Configurar Portal específico")
        console.print("  [D]   🔥 BORRAR TODAS LAS CREDENCIALES")
        console.print("  [0]   🔙 Volver al menú principal\n")

        opc = input("  Selecciona una opción: ").strip().upper()

        if opc == "0":
            break
        
        if opc == "D":
            confirmar = input("  ⚠️  ¿Seguro que quieres borrar TODAS tus credenciales? [s/N]: ").lower()
            if confirmar == "s":
                borrar_todas_las_credenciales_env()
                console.print("[red]🔥 Todas las credenciales han sido eliminadas.[/red]")
            continue
        
        mapping = {
            "1": ("DuocLaboral", "DUOC_EMAIL", "DUOC_PASSWORD"),
            "2": ("ChileTrabajos", "CHILETRABAJOS_EMAIL", "CHILETRABAJOS_PASSWORD"),
            "3": ("LinkedIn", "LINKEDIN_EMAIL", "LINKEDIN_PASSWORD"),
            "4": ("Get on Board", "GETONBOARD_EMAIL", "GETONBOARD_PASSWORD"),
            "5": ("Groq AI", "GROQ_API_KEY", None)
        }

        if opc in mapping:
            nombre, key_user, key_pass = mapping[opc]
            console.print(f"\n[bold yellow]--- Configurando {nombre} ---[/bold yellow]")
            
            if key_pass: # Caso portal con user/pass
                nuevo_user = input(f"  Nuevo Email/Usuario (Enter para omitir): ").strip()
                if nuevo_user:
                    actualizar_variable_env(key_user, nuevo_user)
                    console.print(f"  [green]✅ Usuario de {nombre} actualizado.[/green]")
                
                nueva_pass = input(f"  Nueva Contraseña (Enter para omitir): ").strip()
                if nueva_pass:
                    actualizar_variable_env(key_pass, nueva_pass)
                    console.print(f"  [green]✅ Contraseña de {nombre} actualizada.[/green]")
            else: # Caso solo API Key
                if key_user == "GROQ_API_KEY":
                    console.print(f"\n  [bold cyan]💡 Para obtener tu Groq API Key, regístrate en:[/bold cyan]")
                    console.print(f"  [link=https://console.groq.com/keys]https://console.groq.com/keys[/link]\n")
                
                nueva_key = input(f"  Nueva {key_user.replace('_', ' ')} (Enter para omitir): ").strip()
                if nueva_key:
                    actualizar_variable_env(key_user, nueva_key)
                    console.print(f"  [green]✅ {nombre} actualizado.[/green]")
            
            console.print("\n[dim]Los cambios han sido guardados en el archivo .env[/dim]\n")
        else:
            if opc != "0": console.print("[red]Opción no válida[/red]")


def ejecutar_un_reseteo_total():
    """Limpia todos los datos personales y filtros, volviendo al estado inicial."""
    console.print(Panel(
        "[bold red]☢️ RESETEO MAESTRO ☢️[/bold red]\n\n"
        "Esta acción borrará:\n"
        "1. Todos tus datos personales y experiencia laboral.\n"
        "2. Toda tu configuración de filtros e IA.\n"
        "3. TODAS las contraseñas y correos en .env.\n"
        "4. El historial de postulaciones (Base de Datos).\n\n"
        "[bold yellow]El bot volverá a su estado inicial de fábrica.[/bold yellow]",
        border_style="red"
    ))
    
    confirmar = input("\n  ¿Escribir 'RESETEAR' para confirmar? ").strip().upper()
    if confirmar != 'RESETEAR':
        console.print("[yellow]Abortado. No se borró nada.[/yellow]")
        return

    from config import _DEFAULT_PERFIL, _DEFAULT_FILTROS, DB_PATH, SESSION_PATH
    
    console.print("\n[bold cyan]Limpiando sistema...[/bold cyan]")
    
    # 1. Resetear Perfil y Filtros a defaults
    guardar_perfil(_DEFAULT_PERFIL)
    guardar_filtros(_DEFAULT_FILTROS)
    console.print("  [green]✅ Perfil y Filtros reseteados a valores de fábrica.[/green]")

    # 2. Limpiar .env
    borrar_todas_las_credenciales_env()
    console.print("  [green]✅ Credenciales en .env eliminadas.[/green]")

    # 3. Borrar DB y Sesiones
    for fpath in [DB_PATH, SESSION_PATH]:
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                console.print(f"  [green]✅ Eliminado:[/green] [dim]{os.path.basename(fpath)}[/dim]")
            except: pass
    
    # Re-inicializar la base de datos vacía inmediatamente
    inicializar_db()

    console.print("\n[bold green]✅ EL SISTEMA HA SIDO REINICIADO CON ÉXITO.[/bold green]")
    console.print("[dim]Volviendo al asistente de inicio...[/dim]\n")
    time.sleep(2)
    verificar_onboarding()

def menu_configuracion_ia():
    # Aseguramos que la estructura base exista
    if "ia_config" not in FILTROS:
        FILTROS["ia_config"] = {
            "nacionalidad_ubicacion": "",
            "experiencia_general_anos": "1",
            "lista_posee": [{"habilidad": "Python", "anos": "2"}],
            "lista_no_posee": [{"habilidad": "Java", "anos": "0"}]
        }
        guardar_filtros(FILTROS)
    # Migración de estructura antigua a la nueva por si acaso
    ia_cfg = FILTROS["ia_config"]
    if "experiencia_posee" in ia_cfg:
        if "lista_posee" not in ia_cfg:
            ia_cfg["lista_posee"] = [ia_cfg["experiencia_posee"]]
        del ia_cfg["experiencia_posee"]
    if "experiencia_no_posee" in ia_cfg:
        if "lista_no_posee" not in ia_cfg:
            ia_cfg["lista_no_posee"] = [ia_cfg["experiencia_no_posee"]]
        del ia_cfg["experiencia_no_posee"]
    if "lista_posee" not in ia_cfg: ia_cfg["lista_posee"] = []
    if "lista_no_posee" not in ia_cfg: ia_cfg["lista_no_posee"] = []
    guardar_filtros(FILTROS)

    while True:
        ia_config = FILTROS["ia_config"]
        instrucciones_actuales = FILTROS.get("instrucciones_ia", "")
        
        console.print(Panel.fit(
            "[bold magenta]🧠  Configuración Avanzada de IA[/bold magenta]\n"
            "[dim]Personaliza cómo la IA responde las preguntas de las empresas[/dim]", 
            border_style="magenta"
        ))
        
        exp_gen = ia_config.get('experiencia_general_anos', '1')
        instr_desc = f"[cyan]{instrucciones_actuales}[/cyan]" if instrucciones_actuales else "[yellow]No configurado[/yellow]"
        console.print(f"  [1] 📝 Instrucciones Extra:   {instr_desc}")
        console.print(f"  [2] 📈 Años en el Cargo:      [cyan]{exp_gen} año(s)[/cyan]")
        
        # Opción 3: Memoria Técnica (Consolidado)
        perfil = cargar_perfil()
        kb = perfil.get('base_conocimientos', [])
        desc_kb = ", ".join([f"{x.get('conocimiento','?')}({x.get('anos','0')})" for x in kb[:3]]) + ("..." if len(kb) > 3 else "")
        if not kb: desc_kb = "[yellow]Sin núcleos de memoria[/yellow]"
        console.print(f"  [3] 🧠 MEMORIA TÉCNICA (Skills) [magenta]({len(kb)} núcleos)[/magenta]: [cyan]{desc_kb}[/cyan]")
        
        # Opción 4: Habilidades que NO manejas (Simplificado)
        l_no = ia_config.get('lista_no_posee', [])
        desc_no = ", ".join([x['habilidad'] for x in l_no[:3]]) + ("..." if len(l_no) > 3 else "")
        if not l_no: desc_no = "[yellow]Ninguna configurada[/yellow]"
        console.print(f"  [4] ❌ Habilidades que NO manejas: [cyan]{desc_no}[/cyan]")

        faqs_total = len(perfil.get('preguntas_frecuentes', []))
        faqs_resp = sum(1 for f in perfil.get('preguntas_frecuentes', []) if f.get('respuesta', '').strip())
        console.print(f"  [5] ✏️  Agregar Preguntas de Entrevista [dim](escribe tu respuesta a preguntas clave)[/dim]")
        console.print(f"  [6] 📋 Ver mis Preguntas [{faqs_resp}/{faqs_total} respondidas]")

        console.print("\n  [0] 🔙 Volver al menú principal\n")
        
        opc = input("  Elige qué modificar [0-6]: ").strip()
        
        if opc == "1":
            console.print("\n  [bold cyan]📝 Instrucciones Extra[/bold cyan]")
            console.print("  [white]Escribe aquí cualquier dato adicional o cómo quieres que se presente el bot.[/white]")
            console.print("  [italic yellow]Ejemplo: 'Responde que tengo disponibilidad inmediata y manejo Excel avanzado'.[/italic yellow]")
            nuevas = input("\n  Nuevas instrucciones (0 para borrar, Enter para mantener): ").strip()
            if nuevas == '0':
                FILTROS["instrucciones_ia"] = ""
            elif nuevas:
                FILTROS["instrucciones_ia"] = nuevas
            guardar_filtros(FILTROS)
                
        elif opc == "2":
            console.print("\n  [bold cyan]📈 Años Totales de Experiencia en el Cargo[/bold cyan]")
            val = input(f"  ¿Cuántos años diremos que llevas en '{FILTROS.get('carrera', 'tu cargo')}'? (ej: 2): ").strip()
            if val.isdigit():
                FILTROS["ia_config"]["experiencia_general_anos"] = val
                guardar_filtros(FILTROS)
                
        elif opc == "3":
            menu_base_conocimientos(perfil)
                
        elif opc == "4":
            menu_gestion_habilidades_negativas()
        elif opc == "5":
            menu_agregar_preguntas(perfil)
        elif opc == "6":
            menu_ver_preguntas(perfil)
        elif opc == "0":
            break
        
        if opc in ["1", "2", "3", "4", "5", "6"]:
            console.print("[green]✅  Configuración de IA guardada.[/green]\n")

def menu_gestion_habilidades_negativas():
    """Gestiona la lista de cosas que el usuario NO sabe, sin pedir años."""
    while True:
        ia_cfg = FILTROS["ia_config"]
        lista = ia_cfg.get("lista_no_posee", [])
        
        console.print(Panel.fit("[bold red]❌ Habilidades que NO manejas[/bold red]", border_style="red"))
        console.print("[dim]Esto ayuda a la IA a saber cuándo debe ser honesta sobre lo que no conoces.[/dim]\n")
        
        if not lista:
            console.print("  [yellow]No hay habilidades marcadas como desconocidas.[/yellow]\n")
        else:
            for i, item in enumerate(lista, 1):
                console.print(f"  {i}. [bold]{item['habilidad']}[/bold] -> [red]No conozco[/red]")
            console.print()

        console.print("  [A] ➕ Marcar como desconocida")
        console.print("  [B] 🗑️  Quitar de la lista")
        console.print("  [0] 🔙 Volver")
        
        sub_opc = input("\n  Opción: ").strip().upper()
        
        if sub_opc == "A":
            hab = input("  ¿Qué habilidad NO manejas? (ej: Kubernetes): ").strip()
            if hab:
                # Guardamos años como "0" internamente para evitar romper otras partes, pero no lo mostramos
                ia_cfg["lista_no_posee"].append({"habilidad": hab, "anos": "0"})
                guardar_filtros(FILTROS)
                console.print(f"[green]✅ '{hab}' agregada a la lista negra.[/green]")
        elif sub_opc == "B":
            if not lista: continue
            idx = input("  Número a quitar: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(lista):
                eliminado = ia_cfg["lista_no_posee"].pop(int(idx)-1)
                guardar_filtros(FILTROS)
                console.print(f"[red]🗑️ Quitado: {eliminado['habilidad']}[/red]")
        elif sub_opc == "0":
            break
        elif sub_opc == "0":
            break

def menu_principal_inicio():
    while True:
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        pensamiento = sintetizar_pensamiento()
        
        console.print(Panel(
            f"[bold white]✨ Sistema de Conciencia Artificial - Bot de Empleos ✨[/bold white]\n"
            f"[dim]Bienvenido. Este bot aprenderá de ti para postular en tu nombre.[/dim]\n\n"
            f"[italic cyan]💭 Pensamiento actual:[/italic cyan]\n"
            f"[italic white]\"{pensamiento}\"[/italic white]",
            border_style="blue",
            box=box.DOUBLE
        ))
        
        # Estado actual simplificado
        perfil = cargar_perfil()
        nombre = perfil.get('nombre_completo') or "Candidato Desconocido"
        cargo = FILTROS.get("carrera") or "Por definir"
        
        console.print(f"  [cyan]●[/cyan] Candidato: [cyan]{nombre}[/cyan]")
        console.print(f"  [cyan]●[/cyan] Objetivo:  [cyan]{cargo}[/cyan]")
        console.print(f"  [cyan]●[/cyan] Postulaciones: [bold green]{total_postulaciones()}[/bold green]\n")

        console.print("  [1] 🚀 [bold green]Iniciar Centro de Operaciones[/bold green]")
        console.print("  [2] 👤 [bold blue]Perfil de Usuario[/bold blue]")
        console.print("  [3] 🧠 [bold magenta]Ajustar mi Pensamiento (Config IA)[/bold magenta]")
        console.print("  [4] 🚫 [bold yellow]Gestionar Filtros de Rechazo[/bold yellow]")
        console.print("  [5] 🔑 [bold green]Configurar Accesos (Credenciales)[/bold green]")
        console.print("  [6] 📊 Ver Historial de Postulaciones")
        console.print("  [8] ☢️  [bold red]RESETEO MAESTRO (Borrar Todo)[/bold red]")
        console.print("  [H] ❓ Ayuda / Documentación")
        console.print("  [9] ❌ Desactivarme")
        console.print()
        
        opc = input("  ¿Cuál es tu orden? ").strip()
        
        if opc == "1":
            portal = seleccionar_portal()
            if portal:
                return portal
        elif opc == "2":
            menu_perfil_usuario()
        elif opc == "3":
            menu_configuracion_ia()
        elif opc == "4":
            menu_gestion_filtros_rechazo()
        elif opc == "5":
            menu_configuracion_credenciales()
        elif opc == "6":
            ver_postulaciones()
        elif opc.upper() == "H":
            mostrar_ayuda_sistema()
        elif opc == "8":
            ejecutar_un_reseteo_total()
        elif opc == "9":
            console.print("[dim]Desconectando... 👋[/dim]")
            sys.exit(0)
        else:
            console.print("[red]Opción inválida[/red]")

# ─────────────────────────────────────────────────────────────────
#  VALIDACIONES
# ─────────────────────────────────────────────────────────────────

def es_email_valido(email):
    import re
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def es_rut_valido(rut):
    if not rut: return True # Opcional
    # Validación básica de formato y longitud
    rut = rut.replace(".", "").replace("-", "").upper()
    if not rut[:-1].isdigit():
        return False
    return 1 <= len(rut) <= 10

def es_telefono_valido(tel):
    # Debe ser al menos 8-9 dígitos
    clean_tel = "".join(filter(str.isdigit, tel))
    return len(clean_tel) >= 8

def es_url_valida(url):
    return url.startswith("http") or url.startswith("www")

def verificar_onboarding():
    """Si el perfil está vacío, inicia un asistente interactivo."""
    perfil = cargar_perfil()
    if not perfil.get("nombre_completo"):
        console.print(Panel(
            "[bold cyan]🤖 ASISTENTE DE INICIO[/bold cyan]\n\n"
            "Hola. Veo que es tu primera vez o tu perfil está vacío.\n"
            "Para que yo pueda postular por ti, necesito 'conocer' tu identidad.",
            border_style="cyan",
            box=box.ROUNDED
        ))
        
        input("\n  Presiona Enter para comenzar a alimentar mi conciencia...")
        
        while True:
            nombre = input("\n  1. ¿Cuál es tu nombre completo? ").strip()
            if len(nombre) > 5:
                perfil["nombre_completo"] = nombre
                break
            console.print("[yellow]⚠️ Por favor, ingresa un nombre real válido.[/yellow]")
        
        while True:
            email = input("  2. ¿Cuál es tu email de contacto? ").strip()
            if es_email_valido(email):
                perfil["email"] = email
                break
            console.print("[yellow]⚠️ Email inválido. Ejemplo: usuario@gmail.com[/yellow]")
        
        while True:
            tel = input("  3. ¿Tu número de teléfono? (ej: +569 1234 5678): ").strip()
            if es_telefono_valido(tel):
                perfil["telefono"] = tel
                break
            console.print("[yellow]⚠️ Teléfono inválido. Debe tener al menos 8 dígitos.[/yellow]")
        
        # --- CARRERA OBJETIVO ---
        console.print("\n  [bold cyan]4. ¿Qué cargo o carrera estás buscando?[/bold cyan]")
        console.print("     [dim]Elige de la lista oficial de DuocLaboral o escribe la tuya (con 'm').[/dim]")
        from constantes import DUOC_CARRERAS
        
        while True:
            carrera_elegida = menu_seleccionar_opcion(DUOC_CARRERAS, "Selecciona tu Carrera Objetivo")
            if carrera_elegida:
                break
            console.print("[yellow]⚠️ Este paso es obligatorio. Si no está en la lista usa 'm' para cargo personalizado.[/yellow]")
            time.sleep(1.5)
        
        FILTROS["carrera"] = carrera_elegida
        perfil["cargo_objetivo"] = carrera_elegida
        guardar_filtros(FILTROS)        
        while True:
            rut = input("  5. ¿Cuál es tu RUT/ID? (ej: 12.345.678-9) [Opcional]  Saltar'(Enter): ").strip()
            if not rut or es_rut_valido(rut):
                perfil["rut"] = rut
                break
            console.print("[yellow]⚠️ RUT/ID inválido. Ingresa un formato válido o deja vacío.[/yellow]")

        console.print("\n  [bold cyan]6. Ubicación (Región y Comuna)[/bold cyan]")
        from constantes import DUOC_REGIONES, DUOC_COMUNAS
        
        while True:
            opciones_reg = {"Cualquiera": ""}
            opciones_reg.update(DUOC_REGIONES)
            reg = menu_seleccionar_opcion(opciones_reg, "Selecciona tu Región", "region")
            if reg: break
            console.print("[yellow]⚠️ Selecciona una región válida.[/yellow]")
            time.sleep(1.5)
            
        while True:
            opciones_com = {"Cualquiera": ""}
            opciones_com.update(DUOC_COMUNAS)
            com = menu_seleccionar_opcion(opciones_com, "Selecciona tu Comuna", "comuna")
            if com: break
            console.print("[yellow]⚠️ Selecciona una comuna válida o 'Cualquiera'.[/yellow]")
            time.sleep(1.5)
            
        ubi_final = com if com and com != "Cualquiera" else reg
        if com and com != "Cualquiera" and reg and reg != "Cualquiera":
            ubi_final = f"{com}, {reg}"
        elif reg and reg != "Cualquiera":
            ubi_final = reg
            
        perfil["ubicacion"] = ubi_final
        FILTROS["region"] = reg
        FILTROS["comuna"] = com

        console.print("\n  [bold cyan]7. Ciudad (Para portal ChileTrabajos)[/bold cyan]")
        from constantes import CT_CIUDADES
        
        while True:
            ciu = menu_seleccionar_opcion(CT_CIUDADES, "Selecciona tu Ciudad principal", "ciudad")
            if ciu: break
            console.print("[yellow]⚠️ Selecciona una ciudad válida.[/yellow]")
            time.sleep(1.5)
            
        FILTROS["ciudad"] = ciu

        while True:
            console.print("\n  7. [bold cyan]Sube tu Currículum (CV):[/bold cyan]")
            console.print("     [dim]Sugerencia: Puedes seleccionar el archivo en la ventana que se abrirá, arrastrarlo aquí o escribir la ruta.[/dim]")
            
            # Intentar abrir el selector visual primero
            cv = seleccionar_archivo_pdf()
            
            # Si el selector se cerró sin elegir o no funcionó, pedir manual
            if not cv:
                cv = input("     Ingresa la ruta o arrastra el archivo (.pdf) [Enter para omitir]: ").strip().replace('"', '').replace("'", "")
            
            if not cv:
                break
            
            if not cv.lower().endswith(".pdf"):
                console.print("     [red]❌ El archivo debe ser un PDF.[/red]")
                continue
            
            if os.path.exists(cv):
                # Copiar el CV a la carpeta del bot para asegurar permanencia
                root_bot = os.path.dirname(os.path.abspath(__file__))
                filename = "mi_cv_postulacion.pdf"
                dest_path = os.path.join(root_bot, filename)
                
                try:
                    if os.path.abspath(cv) != os.path.abspath(dest_path):
                        shutil.copy2(cv, dest_path)
                        console.print(f"     [blue]💾 Copia de seguridad creada en la carpeta del bot.[/blue]")
                    
                    actualizar_variable_env("CV_PATH", dest_path)
                    console.print(f"     [green]✅ CV configurado con éxito.[/green]")
                    break
                except Exception as e:
                    console.print(f"     [red]❌ Error al procesar el archivo: {e}[/red]")
                    # Fallback al original si falla la copia
                    actualizar_variable_env("CV_PATH", os.path.abspath(cv))
                    break
            else:
                console.print(f"     [yellow]⚠️ El archivo no existe. Revisa la ruta.[/yellow]")
                confirm_skip = input("     ¿Omitir por ahora? [s/N]: ").lower()
                if confirm_skip == 's': break

        # --- NUEVAS PREGUNTAS DE PERFIL ---
        console.print("\n  [bold cyan]8. Experiencia Laboral / Perfil:[/bold cyan]")
        console.print("     [dim]Ayúdame a saber qué has hecho. Si no tienes experiencia, presiona Enter en 'Empresa'.[/dim]")
        
        while True:
            empresa = input("\n     ➤ 1. Nombre de la empresa (Enter para saltar): ").strip()
            
            if not empresa:
                console.print("\n     [yellow]Entendido, registraremos tu perfil profesional entonces.[/yellow]")
                # Fallback: Solo Resumen
                
                while True:
                    resumen = input("     ➤ Escribe un breve resumen de lo que buscas (Enter para omitir): ").strip()
                    if resumen:
                        perfil["resumen_profesional"] = resumen
                    break
                break
            
            # Si hay empresa, pedir el resto de forma obligatoria
            cargo_exp = input("     ➤ 2. Cargo desempeñado: ").strip()
            fecha = input("     ➤ 3. Periodo (ej: 2021-2023 o 'Actual'): ").strip()
            desc = input("     ➤ 4. Descripción de tus tareas (mín 20 chars): ").strip()
            
            if empresa and cargo_exp and len(desc) >= 20:
                if "experiencia_laboral" not in perfil:
                    perfil["experiencia_laboral"] = []
                perfil["experiencia_laboral"].append({
                    "empresa": empresa,
                    "cargo": cargo_exp,
                    "periodo": fecha,
                    "descripcion": desc
                })
                # Resumen automático
                perfil["resumen_profesional"] = f"Profesional con experiencia como {cargo_exp} en {empresa}. {desc}"
                break
            else:
                console.print("     [yellow]⚠️ Debes completar todos los campos si vas a registrar una experiencia.[/yellow]")


        # --- PREFERENCIAS Y MEMORIA TÉCNICA ---
        console.print("\n  [bold cyan]9. Preferencias de Postulación:[/bold cyan]")
        if "preferencias" not in perfil: perfil["preferencias"] = {}
        
        while True:
            renta = input("     ➤ ¿Tu renta líquida esperada? (ej: 800000) [Solo números]: ").strip()
            if not renta: 
                break
            if renta.isdigit():
                perfil["preferencias"]["renta_esperada"] = renta
                break
            console.print("     [yellow]⚠️ Ingresa solo números (ej: 900000).[/yellow]")

        perfil["preferencias"]["disponibilidad"] = input("     ➤ ¿Tu disponibilidad? (ej: Inmediata): ").strip() or "Inmediata"

        console.print("\n  [bold cyan]10. Alimentar Memoria Técnica (IA):[/bold cyan]")
        console.print("     [dim]Dime qué sabes hacer para que yo pueda responder pruebas técnicas por ti.[/dim]")
        
        if "base_conocimientos" not in perfil: perfil["base_conocimientos"] = []
        
        while True:
            con = input("\n     ➤ ¿Habilidad o conocimiento? (ej: Python, Excel) [Enter para terminar]: ").strip()
            if not con: break
            
            while True:
                anos = input(f"     ➤ ¿Cuántos años de experiencia tienes en '{con}'?: ").strip()
                if anos.isdigit():
                    perfil["base_conocimientos"].append({
                        "conocimiento": con,
                        "anos": anos,
                        "detalles": f"Experiencia de {anos} años en {con}."
                    })
                    console.print(f"     [green]✔ {con} ({anos} años) agregado.[/green]")
                    break
                console.print("     [yellow]⚠️ Ingresa solo el número de años.[/yellow]")

        # --- CONFIGURACIÓN DE GROQ IA ---
        console.print("\n  [bold magenta]11. Inteligencia Artificial (Groq):[/bold magenta]")
        console.print("     [dim]Para que yo pueda pensar y responder por ti, necesito una API Key de Groq.[/dim]")
        console.print("     [cyan]💡 Obtén tu llave GRATIS aquí:[/cyan] [link=https://console.groq.com/keys]https://console.groq.com/keys[/link]")
        
        while True:
            gkey = input("\n     ➤ Pega tu Groq API Key aquí (Enter para omitir): ").strip()
            if not gkey:
                console.print("     [yellow]⚠️ Podrás configurarla luego en el menú de 'Credenciales'.[/yellow]")
                break
            if len(gkey) > 20: # Validación básica de longitud
                actualizar_variable_env("GROQ_API_KEY", gkey)
                console.print("     [green]✅ Groq API Key configurada correctamente.[/green]")
                break
            console.print("     [yellow]⚠️ La API Key parece inválida. Intenta nuevamente.[/yellow]")

        # --- REDIRECCIÓN AL MENÚ DE CREDENCIALES ---
        console.print("\n  [bold green]12. Configuración Final de Accesos:[/bold green]")
        console.print("     [dim]Te enviaré al gestor de credenciales para que configures tus portales ahora.[/dim]")
        input("\n     Presiona Enter para abrir el gestor de accesos...")
        
        menu_configuracion_credenciales()

        guardar_perfil(perfil)
        console.print("\n[bold green]✅ ¡Excelente! Mi conciencia ha sido alimentada con éxito.[/bold green]")
        console.print("[dim]Puedes ver y editar todo esto en el menú de 'Alimentar Conciencia'.[/dim]\n")
        time.sleep(2)

def mostrar_ayuda_sistema():
    """Muestra una guía rápida de uso del bot."""
    console.print(Panel(
        "[bold cyan]📖 GUÍA DE USO - DUOCLABORAL BOT[/bold cyan]\n\n"
        "[bold white]1. Configuración Inicial[/bold white]\n"
        "   • Ve a [bold blue]Perfil de Usuario[/bold blue] para completar tus datos reales.\n"
        "   • En [bold green]Configurar Accesos[/bold green], ingresa tus credenciales de los portales.\n"
        "   • [IMPORTANT] Necesitas una [bold magenta]Groq API Key[/bold magenta] para que la IA funcione.\n"
        "     Obtenla gratis en: [link=https://console.groq.com/keys]https://console.groq.com/keys[/link]\n\n"
        "[bold white]2. Modos de Operación[/bold white]\n"
        "   • [bold green]Revisión Manual[/bold green]: El bot te muestra cada oferta y tú decides si postular.\n"
        "   • [bold red]Modo Automático[/bold red]: El bot postula sin preguntar.\n"
        "   • [bold yellow]⚠️ Cómo Detener[/bold yellow]: Presiona [bold red]Ctrl + C[/bold red] en cualquier momento para abortar la misión.\n\n"
        "[bold white]3. Credenciales y Seguridad[/bold white]\n"
        "   • [bold cyan]Obligatorio[/bold cyan]: Debes poner tu correo y clave real de los portales (ej: Duoc) para que el bot pueda entrar.\n"
        "   • Tus datos se guardan [bold green]solo localmente[/bold green] en tu archivo .env.\n\n"
        "[dim]Para más detalles, revisa el archivo 'help.txt' en la carpeta raíz.[/dim]",
        title="[bold white]CENTRO DE AYUDA[/bold white]",
        border_style="cyan",
        box=box.DOUBLE
    ))
    input("\n  Presiona Enter para volver...")

if __name__ == "__main__":
    try:
        inicializar_db()
        verificar_onboarding()
        
        while True:
            # Menú principal inicial
            nombre_portal = menu_principal_inicio()

            # Una vez seleccionado el portal, entramos al menú de acciones de ese portal
            while True:
                opcion = mostrar_menu(nombre_portal)

                if opcion == "0":
                    menu_ajustar_filtros_antes_de_buscar(nombre_portal)
                    continue # Volver a mostrar el submenú del portal
                elif opcion == "1":
                    # Al iniciar, si el filtro de Duoc parece incorrecto, forzar confirmación una vez
                    _, msg = validar_region_portal(nombre_portal, FILTROS.get("region", ""))
                    if "ADVERTENCIA" in msg:
                        console.print(f"\n{msg}")
                        conf = input("  ¿Deseas corregir los filtros antes de iniciar? [S/n]: ").strip().lower()
                        if conf != 'n':
                            menu_ajustar_filtros_antes_de_buscar(nombre_portal)
                            continue # Volver a mostrar el submenú del portal
                    
                    run_bot(nombre_portal, modo_revision=True)
                elif opcion == "2":
                    console.print("\n[red bold]⚠️  MODO AUTOMÁTICO: postulará SIN pedir confirmación[/red bold]")
                    confirmar = input("  ¿Estás seguro? [s/N]: ").strip().lower()
                    if confirmar == "s":
                        run_bot(nombre_portal, modo_revision=False)
                elif opcion == "5":
                    solo_escanear(nombre_portal)
                elif opcion == "6":
                    # Al darle a Cambiar portal, rompemos el bucle secundario
                    # y volvemos al menú principal inicial
                    break 
                elif opcion == "9":
                    console.print("[dim]Desconectando... 👋[/dim]")
                    sys.exit(0)
                else:
                    console.print("[red]Opción inválida[/red]")

                input("\n  Presiona Enter para continuar...")
    except KeyboardInterrupt:
        console.print("\n[yellow]🔌 Sesión interrumpida por el usuario. Cerrando...[/yellow]")
        sys.exit(0)
