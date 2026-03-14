"""
scraper.py — Playwright: login, scraping de ofertas y extracción de formularios
"""
import time
import random
from rich.console import Console

console = Console()

# ── Importaciones locales ──
import json
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
# Importación dinámica en crear_browser para mayor compatibilidad

from config import (
    DUOC_EMAIL, DUOC_PASSWORD, LOGIN_URL, OFERTAS_URL, FILTROS, BASE_URL, SESSION_PATH
)


def _pausa(min_s=2.5, max_s=5.5):
    """Pausa aleatoria para simular comportamiento humano (tiempos más largos)."""
    time.sleep(random.uniform(min_s, max_s))


def scroll_aleatorio(page: Page):
    """Realiza un scroll suave aleatorio para simular lectura."""
    try:
        movimiento = random.randint(100, 500)
        page.mouse.wheel(0, movimiento)
        _pausa(0.5, 1.5)
    except Exception:
        pass


def crear_browser(headless=False):
    """Crea y retorna (playwright, browser, context, page)."""
    p = sync_playwright().start()
    # Argumentos extra para evadir la detección de bots
    browser = p.chromium.launch(
        headless=headless,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled"
        ]
    )
    context = browser.new_context(
        no_viewport=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Intentar cargar sesión guardada
    try:
        with open(SESSION_PATH, "r") as f:
            storage = json.load(f)
        context.add_cookies(storage.get("cookies", []))
    except FileNotFoundError:
        pass

    page = context.new_page()
    
    # Intentar aplicar stealth de varias formas según la versión de la librería
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        try:
            from playwright_stealth import stealth
            stealth(page)
        except Exception:
            try:
                from playwright_stealth.stealth import Stealth
                # En algunas versiones nuevas, Stealth().use_sync(p) es la forma,
                # pero para una página individual a veces funciona pasarla.
                # Si todo falla, al menos el bot sigue.
                pass 
            except Exception:
                pass
            
    return p, browser, context, page


def guardar_sesion(context: BrowserContext):
    """Guarda las cookies de la sesión actual."""
    cookies = context.cookies()
    with open(SESSION_PATH, "w") as f:
        json.dump({"cookies": cookies}, f)


def login(page: Page, context: BrowserContext) -> bool:
    """
    Realiza el login en DuocLaboral.
    Retorna True si el login fue exitoso.
    """
    page.goto(LOGIN_URL, timeout=60000)
    _pausa()

    # Verificar si ya está logueado
    if "login" not in page.url:
        print("✅ Sesión activa detectada")
        return True

    try:
        # Buscar campos de login (pueden variar, intentamos varios selectores)
        email_sel = '#username, input[name="LoginForm[username]"], input[type="email"]'
        pass_sel  = '#password, input[name="LoginForm[password]"], input[type="password"]'

        page.wait_for_selector(email_sel, timeout=10000)
        
        # Limpiar campos primero para evitar duplicados (ej: si el browser los autofilló)
        page.fill(email_sel, "")
        page.type(email_sel, DUOC_EMAIL.strip(), delay=random.randint(50, 150))
        _pausa(1.0, 2.0)
        
        page.fill(pass_sel, "")
        page.type(pass_sel, DUOC_PASSWORD.strip(), delay=random.randint(50, 150))
        _pausa(1.0, 2.0)
        
        # Mover un poco el mouse antes de hacer clic
        try:
            box = page.locator('#userLoginSubmit, button[type="submit"], input[type="submit"]').bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                _pausa(0.3, 0.8)
        except Exception:
            pass

        page.click('#userLoginSubmit, button[type="submit"], input[type="submit"]')

        # Esperar hasta 15 segundos a que la URL cambie (salga del login)
        try:
            page.wait_for_function('window.location.pathname !== "/login"', timeout=15000)
        except Exception:
            pass # Si falla por timeout, igual se evalúa en el siguiente if
        
        _pausa(1, 2)

        if "login" not in page.url:
            print("✅ Login exitoso")
            guardar_sesion(context)
            return True
        else:
            print(f"❌ Login fallido — la URL no cambió: {page.url}")
            return False
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return False


def aplicar_filtros_avanzados(page: Page, carrera: str):
    """
    Interactúa con el panel de filtros para seleccionar la carrera.
    """
    try:
        page.goto(OFERTAS_URL, timeout=60000)
        _pausa(2, 4)
        
        # 1. Click en el botón "Filtros"
        btn_filtros = page.query_selector('button:has-text("Filtros"), .btn-filters, .filters-button')
        if btn_filtros:
            btn_filtros.scroll_into_view_if_needed()
            btn_filtros.click()
            _pausa(1, 2)
        
        # Selector robusto basado en el HTML exacto proporcionado por el usuario (Selectize)
        console.print("[dim]🔎 Buscando selector de Carrera (Selectize)...[/dim]")
        
        # Primero, hacer clic en la caja visible del input
        input_container_sel = ".selectize-input"
        page.wait_for_selector(input_container_sel, timeout=10000)
        page.click(input_container_sel)
        _pausa(0.5, 1.0)
        
        # Ahora el input de búsqueda debería estar interactivo
        input_selectize = "input#Search_genericCareer-selectized"
        input_el = page.wait_for_selector(input_selectize, state="visible", timeout=5000)
        
        if input_el:
            # Limpiar campo si es necesario y escribir
            input_el.fill("")
            page.keyboard.type(carrera, delay=150) # Más lento, pareciendo humano
            _pausa(3.0, 4.0) # Esperar a que el dropdown procese la búsqueda internamente por AJAX
            
            # Navegar explícitamente y mantener presionadas las teclas
            page.keyboard.press("ArrowDown", delay=200) 
            _pausa(1.0, 1.5)
            page.keyboard.press("Enter", delay=300)
            _pausa(1.5, 2.5)
            console.print(f"  [green]✅ Carrera '{carrera}' seleccionada en UI.[/green]")
        else:
            console.print("  [yellow]⚠️ No se encontró el input selectize interactivo.[/yellow]")
        
        # 3. Click en "Aplicar filtros" o "Buscar"
        # El botón naranja grande suele ser el disparador
        btn_aplicar = page.query_selector('button:has-text("Aplicar filtros"), button:has-text("Buscar"), .orange-button, #search-btn')
        if btn_aplicar:
            btn_aplicar.scroll_into_view_if_needed()
            btn_aplicar.click()
            console.print("  [cyan]🚀 Aplicando filtros y recargando resultados...[/cyan]")
            _pausa(4, 6) # Esperar recarga intensa
            
            # 4. VALIDACIÓN ROBUSTA DEL DOM: Verificar que el filtro se aplicó realmente
            # Buscamos si existe alguna burbuja de filtro activo ("filters-active", "tag", etc.)
            # Si no dice "Ingenier", el filtro falló y no deberíamos buscar nada
            texto_pantalla = page.locator("body").inner_text().lower()
            if "informátic" not in texto_pantalla and "ingenier" not in texto_pantalla:
                raise Exception("Fallo Crítico: El filtro de Carrera NO se aplicó en la página web. Deteniendo para evitar postular a carreras incorrectas.")
                
            console.print("  [green]✅ Validación visual superada: Filtro de carrera activo en DOM.[/green]")
        else:
            console.print("  [yellow]⚠️ No se halló el botón 'Aplicar' / 'Buscar'[/yellow]")
            
    except Exception as e:
        print(f"⚠️ Error al aplicar filtros manuales: {e}. Intentando continuar...")


def obtener_ofertas(page: Page, paginas: int = 3) -> list[dict]:
    """
    Scraping del listado de ofertas.
    """
    ofertas = []

    for num_pagina in range(1, paginas + 1):
        # ── NUEVO: NO RECARGAR SI ESTAMOS EN LA PÁGINA 1 ──
        # La UI de DuocLaboral (aplicar_filtros_avanzados) ya recargó la página con los filtros.
        # Volver a navegar a url = f"{OFERTAS_URL}?page=1" destruye los filtros generados por el botón naranja.
        
        if num_pagina > 1:
            console.print("  [dim]Buscando botón Siguiente en el paginador...[/dim]")
            btn_siguiente = page.query_selector('.pagination a[rel="next"], .pagination li:last-child a, a:has-text("Siguiente"), a:has-text("Next")')
            if btn_siguiente:
                btn_siguiente.scroll_into_view_if_needed()
                btn_siguiente.click()
                console.print(f"  [dim]Navegando a página {num_pagina} (Clic Siguiente)[/dim]")
                _pausa(3, 5) # Esperar a que recargue la página la tabla
            else:
                console.print("  [yellow]⚠️ No se encontró botón para avanzar a la página siguiente. Fin de resultados.[/yellow]")
                break
        else:
            console.print(f"[dim]📄 Escaneando página 1 (filtros actuales)...[/dim]")

        # Esperar que cargue la lista
        try:
            # Selector exacto del HTML proporcionado por el usuario
            # <a href="/jobs/856267" class="btn btn-primary job-card-apply-btn" ...>Postular...</a>
            selector_ofertas = ".job-card, .job-offer, article" # Selector general del contenedor de la tarjeta, si es que lo hay
            page.wait_for_selector(selector_ofertas, timeout=10000)
        except Exception:
            console.print(f"  [yellow]⚠️  No se encontraron más ofertas en página {num_pagina}[/yellow]")
            break

        # Extraer tarjetas de ofertas
        tarjetas = page.query_selector_all("a[href*='/trabajar-en-'], a[href*='/trabajo/trabajar']")

        if not tarjetas:
            # Selector alternativo
            tarjetas = page.query_selector_all(".job-listing a, .oferta-card a, h2 a, h3 a")

        print(f"  Encontradas {len(tarjetas)} ofertas")

        for tarjeta in tarjetas:
            try:
                # Scroll suave de vez en cuando
                if random.random() < 0.3:
                    scroll_aleatorio(page)
                    
                href = tarjeta.get_attribute("href") or ""
                if not href or "/trabajar" not in href:
                    continue

                # Extraer ID de la URL
                oferta_id = href.rstrip("/").split("/")[-1]
                
                # Intentar buscar un título dentro de la tarjeta
                titulo = ""
                titulo_el = tarjeta.query_selector("h2, h3, h4, .job-title, .titulo, strong, b")
                if titulo_el:
                    titulo = titulo_el.inner_text().strip()
                
                # Si sigue vacío, buscar en atributos del link
                if not titulo:
                    titulo = tarjeta.get_attribute("title") or tarjeta.get_attribute("aria-label") or ""
                
                # Último recurso: texto completo del link
                if not titulo:
                    texto_completo = tarjeta.inner_text().strip()
                    titulo = texto_completo.split('\n')[0] if texto_completo else "Sin título"
                
                # Si el título es muy corto, tal vez no sea el título real
                if len(titulo) < 3:
                    titulo = "Oferta sin título claro"
                    
                # Botón "Postular" en la tarjeta (Disparador para entrar)
                btn_postular_sel = "button:has-text('Postular'), .btn-postular, .postular-btn, a:has-text('Postular')"
                btn_postular = tarjeta.query_selector(btn_postular_sel)
                
                url_oferta = f"https://duoclaboral.cl{href}" if href.startswith("/") else href

                # Evitar duplicados en esta sesión
                if any(o.get("id") == oferta_id for o in ofertas):
                    continue

                ofertas.append({
                    "id": oferta_id,
                    "titulo": titulo,
                    "empresa": "",   # Se extrae en detalle
                    "url": url_oferta,
                    "btn_postular_selector": btn_postular_sel if btn_postular else None
                })
            except Exception:
                continue

        _pausa(2, 5)

    return ofertas


def obtener_detalle_oferta(page: Page, url: str) -> dict:
    """
    Obtiene el detalle de una oferta: descripción, empresa y preguntas del formulario.
    """
    page.goto(url, timeout=60000)
    _pausa(3, 6) # Leer oferta toma más tiempo

    # Simular lectura haciendo scrolls pequeños
    for _ in range(random.randint(2, 4)):
        scroll_aleatorio(page)

    detalle = {
        "titulo": "Sin título",
        "descripcion": "",
        "empresa": "Empresa no especificada",
        "preguntas": [],        # Lista de {label, selector, tipo}
        "renta_selector": None,
        "submit_selector": None,
    }

    try:
        # Título de la oferta (suele ser el H1 principal)
        titulo_h1 = page.query_selector("h1")
        if titulo_h1:
            detalle["titulo"] = titulo_h1.inner_text().strip()

        # Descripción: capturamos TODO el texto visible de la página para la IA
        try:
            # Primero intentamos el contenedor de oferta específico
            page_text = page.evaluate("""
                () => {
                    // Eliminar scripts, estilos y nav de la muestra
                    const garbage = document.querySelectorAll('script,style,nav,footer,header');
                    garbage.forEach(el => el.remove());
                    return document.body ? document.body.innerText : '';
                }
            """).strip()
            if page_text and len(page_text) > 100:
                detalle["descripcion"] = page_text
        except Exception:
            body_el = page.query_selector("body")
            if body_el:
                detalle["descripcion"] = body_el.inner_text()[:10000]

        # Empresa
        emp_el = page.query_selector(".company-name, .empresa, h2.company, .job-company, h2, .companyTitle")
        if emp_el:
            detalle["empresa"] = emp_el.inner_text().strip()

        # Ubicación (Lógica corregida)
        loc_el = page.query_selector(".location, .ubicacion, [title*='Ubicación'], .job-location, .icono-ubicacion + span")
        if not loc_el:
            # Intentar uno por uno para no romper el selector engine
            for txt in ["text=/Región/i", "text=/Ciudad/i"]:
                loc_el = page.query_selector(txt)
                if loc_el: break

        if loc_el:
            detalle["ubicacion"] = loc_el.inner_text().strip()
        else:
            detalle["ubicacion"] = "No especificada"

        # ── Sección de postulación ─────────────────────────────────────────
        # Selectores más estrictos para el contenedor de postulación (basado en HTML proporcionado o contenedor general)
        form_container_selectors = [
            "form:has(button#sendApplication)",
            "form.job-apply-form",
            ".application-form", 
            "#postulacion",
            ".postulacion-container"
        ]
        
        form_container = None
        for sel in form_container_selectors:
            form_container = page.query_selector(sel)
            if form_container:
                break
        
        textareas = []
        if form_container:
            textareas = form_container.query_selector_all("textarea")
        
        # Ya no hacemos fallback a toda la página para evitar textareas de footer (contacto, etc.)
        # Si no está en el form de postulación, no hay preguntas.

        if textareas:
            for i, ta in enumerate(textareas):
                label = ""
                try:
                    js_eval = """
                    el => {
                        // 1. Buscar etiqueta <label> vinculada por 'for'
                        if (el.id) {
                            let lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                        }
                        // 2. Buscar texto en hermanos anteriores inmediatos
                        let prev = el.previousElementSibling;
                        if (prev && prev.innerText.trim()) return prev.innerText.trim();
                        
                        // 3. Buscar en el contenedor más cercano (wrap)
                        let wrap = el.closest('div.form-group, div.field, div.mb-3, .form-item, .form-textarea, .field-wrapper, .wpcf7-form-control-wrap, .textarea-container, td, li');
                        if (wrap) {
                            // Buscar cualquier elemento de texto común antes del textarea dentro del wrap
                            let labels = wrap.querySelectorAll('label, p, span, strong, b, h1, h2, h3, h4, h5, .label, .title');
                            for (let l of labels) {
                                if (l.innerText.trim()) return l.innerText.trim();
                            }
                        }
                        // 4. Buscar en el abuelo si el wrap falló
                        let parent = el.parentElement;
                        if (parent && parent.innerText.trim().length < 500) {
                             // Solo si el texto no es gigante (evitar traer toda la pág)
                             return parent.innerText.split('\\n')[0].trim();
                        }
                        return '';
                    }
                    """
                    extraido = ta.evaluate(js_eval)
                    label = extraido.strip() if extraido else f"Pregunta {i+1}"
                except Exception:
                    label = f"Pregunta {i+1}"

                if detalle.get("preguntas") is None:
                    detalle["preguntas"] = []
                detalle["preguntas"].append({
                    "label": label,
                    "indice": i,
                    "selector": f"textarea:nth-of-type({i+1})",
                })

            # Buscar campo de renta (input numérico o específico)
            renta_sel = 'input[placeholder*="número"], input[placeholder*="Sólo números"], input[placeholder*="numeros"], input[name*="salary"], input[name*="pretension"], input[id*="salary"]'
            renta_el = (form_container.query_selector(renta_sel) if form_container else None) or page.query_selector(renta_sel)
            if renta_el:
                detalle["renta_selector"] = renta_sel
        else:
            # Si no hay formulario visible ni textareas, no detectamos preguntas
            detalle["preguntas"] = []

        # Botón de envío exacto
        btn_selector = 'button#sendApplication.job-apply-btn, button:has-text("Enviar postulación"), button:has-text("Enviar postulacion")'
        
        btn = None
        if form_container:
            btn = form_container.query_selector(btn_selector)
        if not btn:
            btn = page.query_selector(btn_selector)
            
        if btn:
            detalle["submit_selector"] = btn_selector

    except Exception as e:
        print(f"  ⚠️  Error extrayendo detalle: {e}")

    return detalle
