"""
portal.py — Portal Get on Board (getonbrd.com)
Login vía Google OAuth. Postulación directa en el portal.
"""
import json
import random
import time
import re
import os
from urllib.parse import quote
from playwright.sync_api import Page, BrowserContext
from rich.console import Console
from rich.panel import Panel

from config import GETONBOARD_EMAIL, GETONBOARD_PASSWORD, SESSION_PATH, cargar_perfil
from database import ya_postule, registrar_postulacion
from ai_responder import responder_pregunta, resumir_oferta
from portales.base import PortalBase

console = Console()

BASE_URL  = "https://www.getonbrd.com"
LOGIN_URL = "https://www.getonbrd.com/webpros/login?locale=es"
JOBS_URL  = "https://www.getonbrd.com/myjobs?locale=es" # This is for "Jobs for you"
GOOGLE_LOGIN_BTN = "a[href*='google'][href*='auth'], a:has-text('Google'), button:has-text('Google')"


def _pausa(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))


def _scroll(page: Page, veces: int = 3):
    for _ in range(veces):
        page.mouse.wheel(0, random.randint(300, 700))
        _pausa(0.4, 1.0)


class GetOnBoardPortal(PortalBase):

    def __init__(self, page: Page, context: BrowserContext):
        super().__init__(page, context)
        self.nombre = "Get on Board"

    # ─────────────────────────────────────────────────────────────────
    #  LOGIN vía Google OAuth
    # ─────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Inicia sesión en Get on Board a través de Google OAuth."""
        url_inicio = f"{BASE_URL}?locale=es"
        console.print(f"[cyan]🌐 Navegando a {url_inicio}...[/cyan]")
        try:
            self.page.goto(url_inicio, timeout=60000)
            _pausa(2, 4)
        except Exception as e:
            console.print(f"[red]❌ Error de red: {e}[/red]")
            return False

        # ── Verificar sesión activa ──
        if self._esta_logueado():
            console.print("✅ Sesión activa detectada en Get on Board")
            return True

        # ── Abrir dropdown "Ingresa" ──
        try:
            console.print("[dim]  Buscando botón 'Ingresa'...[/dim]")
            btn_ingresa = self.page.locator(
                'button.gb-btn--outlined.dropdown-toggle, '
                'button.gb-login__label, '
                'button:has-text("Ingresa")'
            ).first
            btn_ingresa.wait_for(timeout=10000)
            btn_ingresa.click()
            _pausa(0.8, 1.5)
        except Exception as e:
            console.print(f"[yellow]⚠️  No se encontró el dropdown 'Ingresa'. Intentando ir directo a login: {e}[/yellow]")

        # ── Clic en "Profesionales" ──
        try:
            link_profesionales = self.page.locator(
                'a[href*="/webpros/login"]'
            ).first
            link_profesionales.wait_for(timeout=6000)
            link_profesionales.click()
            _pausa(2, 3)
        except Exception:
            # Si falla el dropdown, ir directo al login URL
            console.print("[dim]  Navegando directo a la página de login...[/dim]")
            self.page.goto(LOGIN_URL, timeout=60000)
            _pausa(2, 3)

        # ── Si ya está en el portal (sesión), listo ──
        if self._esta_logueado():
            console.print("✅ Sesión recuperada")
            return True

        # ── Buscar y clicar el botón de Google OAuth ──
        try:
            console.print("[dim]  Buscando botón de inicio con Google...[/dim]")
            btn_google = self.page.locator(
                'a[href*="google"][href*="auth"], '
                'a:has-text("Google"), '
                '.gb-btn:has-text("Google"), '
                'a.omniauth-btn:has-text("Google")'
            ).first
            btn_google.wait_for(timeout=10000)
            btn_google.click()
            console.print("[dim]  Click en Google OAuth. Esperando redireccionamiento...[/dim]")
            _pausa(3, 6)
        except Exception as e:
            console.print(f"[yellow]⚠️  Botón Google no encontrado: {e}[/yellow]")
            console.print("[dim]  Intentando flujo manual: email + contraseña...[/dim]")
            return self._login_email()

        # ── Manejar la pantalla de cuentas de Google ──
        return self._manejar_google_oauth()

    def _manejar_google_oauth(self) -> bool:
        """Completa el flujo de Google OAuth seleccionando/ingresando la cuenta."""
        try:
            # Esperar a que abra la ventana de Google (puede ser en la misma pestaña o popup)
            _pausa(2, 4)
            current_url = self.page.url

            # Si hay un popup de Google, manejarlo; si no, la página actual es de Google
            if "accounts.google.com" in current_url or "google.com" in current_url:
                google_page = self.page
            else:
                # Puede haber un popup
                try:
                    with self.page.context.expect_page(timeout=8000) as page_info:
                        google_page = page_info.value
                        google_page.wait_for_load_state("domcontentloaded")
                except Exception:
                    google_page = self.page

            return self._rellenar_google(google_page)

        except Exception as e:
            console.print(f"[red]❌ Error en Google OAuth: {e}[/red]")
            return False

    def _rellenar_google(self, google_page: Page) -> bool:
        """Rellena email y contraseña en el formulario de Google."""
        try:
            console.print(f"[dim]  URL Google: {google_page.url}[/dim]")

            # ── Email ──
            # Puede haber una lista de cuentas o el input directo
            cuenta_btn = google_page.locator(
                f'[data-email="{GETONBOARD_EMAIL}"], '
                f'li:has-text("{GETONBOARD_EMAIL}"), '
                f'div[data-identifier="{GETONBOARD_EMAIL}"]'
            ).first

            if cuenta_btn.count() > 0:
                console.print("[dim]  Cuenta encontrada en la lista → haciendo clic...[/dim]")
                cuenta_btn.click()
                _pausa(2, 4)
            else:
                # Input de email
                email_input = google_page.locator('input[type="email"]').first
                email_input.wait_for(timeout=15000)
                email_input.click()
                email_input.fill("")
                email_input.press_sequentially(GETONBOARD_EMAIL, delay=random.randint(80, 200))
                _pausa(0.5, 1)
                google_page.locator('#identifierNext, button:has-text("Siguiente"), button:has-text("Next")').first.click()
                _pausa(2, 4)

            # ── Contraseña ──
            pass_input = google_page.locator('input[type="password"]').first
            pass_input.wait_for(timeout=15000)
            pass_input.click()
            pass_input.fill("")
            pass_input.press_sequentially(GETONBOARD_PASSWORD, delay=random.randint(80, 200))
            _pausa(0.5, 1)
            google_page.locator('#passwordNext, button:has-text("Siguiente"), button:has-text("Next")').first.click()
            _pausa(4, 7)

            # ── Esperar redirección de vuelta a getonbrd ──
            console.print("[dim]  Esperando redirección a Get on Board...[/dim]")
            try:
                self.page.wait_for_url("*getonbrd.com*", timeout=25000)
            except Exception:
                _pausa(3, 5)

            if self._esta_logueado():
                console.print("✅ Login con Google exitoso en Get on Board")
                self._guardar_sesion()
                return True
            else:
                console.print(f"[red]❌ Login no confirmado. URL: {self.page.url}[/red]")
                return False

        except Exception as e:
            console.print(f"[red]❌ Error rellenando Google: {e}[/red]")
            return False

    def _login_email(self) -> bool:
        """Fallback: login con email/contraseña directamente en Get on Board."""
        try:
            email_sel = 'input[name="webpro[email]"], input[type="email"], input[name="email"]'
            pass_sel  = 'input[name="webpro[password]"], input[type="password"], input[name="password"]'

            self.page.wait_for_selector(email_sel, timeout=10000)
            self.page.fill(email_sel, "")
            self.page.type(email_sel, GETONBOARD_EMAIL, delay=random.randint(60, 150))
            _pausa(0.5, 1)

            self.page.fill(pass_sel, "")
            self.page.type(pass_sel, GETONBOARD_PASSWORD, delay=random.randint(60, 150))
            _pausa(0.5, 1)

            self.page.click('button[type="submit"], input[type="submit"]')
            _pausa(2, 4)

            if self._esta_logueado():
                console.print("✅ Login email exitoso")
                self._guardar_sesion()
                return True
            else:
                console.print(f"[red]❌ Login fallido. URL: {self.page.url}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]❌ Error en login email: {e}[/red]")
            return False

    def _esta_logueado(self) -> bool:
        """Verifica si la sesión está activa y asegura que el idioma sea español."""
        url = self.page.url
        logueado = (
            "getonbrd.com" in url
            and "login" not in url
            and "sign" not in url
            and any(x in url for x in ["/myjobs", "/misempleos", "/webpros", "/applications", "/invitations", "/home", "/jobs/search", "/empleos", "/empleos/search"])
        ) or (
            "getonbrd.com" in url
            and self.page.locator('.username, .gb-header-avatar, a[href*="/webpros/logout"]').count() > 0
        )
        
        if logueado:
            # Detectar si el idioma es inglés y cambiar a español si es necesario
            try:
                # El seleccionador de idioma suele estar en el sidebar o footer
                lang_btn = self.page.locator('button:has-text("English"), a:has-text("English"), .gb-sidebar button:has-text("English")').first
                if lang_btn.count() > 0:
                    console.print("[dim]  🌐 Detectado idioma inglés, intentando cambiar a español...[/dim]")
                    lang_btn.click()
                    _pausa(0.5, 1)
                    esp_btn = self.page.locator('a:has-text("Español"), button:has-text("Español"), [data-locale="es"]').first
                    if esp_btn.count() > 0:
                        esp_btn.click()
                        _pausa(2, 4)
                        # También forzar en URL por si acaso
                        if "locale=es" not in self.page.url:
                            curr_url = self.page.url
                            char = "&" if "?" in curr_url else "?"
                            self.page.goto(f"{curr_url}{char}locale=es")
            except Exception:
                pass
                
        return logueado

    # ─────────────────────────────────────────────────────────────────
    #  FILTROS DE BÚSQUEDA
    # ─────────────────────────────────────────────────────────────────

    def aplicar_filtros_avanzados(self, carrera: str, region: str):
        """Navega a la búsqueda de empleos basada en la carrera y región."""
        query = carrera
        if region:
            query += f" {region}"
        
        keyword = quote(query)
        # URL de búsqueda con locale español
        search_url = f"{BASE_URL}/empleos/search?query={keyword}&locale=es"
        
        console.print(f"[cyan]🔍 Buscando empleos para '{carrera}' en {region or 'cualquier ubicación'}...[/cyan]")
        try:
            self.page.goto(search_url, timeout=60000)
            self.page.wait_for_load_state("domcontentloaded")
            _pausa(3, 5)
            
            # Verificar si hay resultados o si redirigió a algún lado raro
            if "search" in self.page.url:
                console.print(f"[green]✅ Búsqueda cargada para: {carrera} | {region}[/green]")
            else:
                console.print(f"[yellow]⚠️  La URL cambió a: {self.page.url}. Podría no haber resultados.[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error navegando a la búsqueda: {e}[/red]")

    # ─────────────────────────────────────────────────────────────────
    #  OBTENER OFERTAS
    # ─────────────────────────────────────────────────────────────────

    def obtener_ofertas(self, paginas: int = 3, num_pagina_actual: int = 1) -> list[dict]:
        """Extrae las ofertas de empleo de la página actual."""
        console.print(f"[dim]📄 Escaneando página {num_pagina_actual}...[/dim]")
        ofertas = []

        if num_pagina_actual > 1:
            # Buscar enlace "Siguiente" o número de página
            btn_sig = self.page.locator(
                f'a[rel="next"], '
                f'.pagination a[aria-label*="{num_pagina_actual}"], '
                f'.pagination a:has-text("{num_pagina_actual}")'
            ).first
            if btn_sig.count() > 0:
                btn_sig.scroll_into_view_if_needed()
                btn_sig.click()
                _pausa(2, 4)
                self.page.wait_for_load_state("domcontentloaded")
            else:
                console.print("[yellow]⚠️  No hay página siguiente.[/yellow]")
                return []

        # Esperar tarjetas de oferta
        try:
            self.page.wait_for_selector('a.gb-results-list__item', timeout=12000)
        except Exception:
            # Re-verificar si estamos en español si no encontramos nada
            if "locale=es" not in self.page.url:
                curr_url = self.page.url
                char = "&" if "?" in curr_url else "?"
                self.page.goto(f"{curr_url}{char}locale=es")
                _pausa(2, 4)
                
            try:
                self.page.wait_for_selector('a.gb-results-list__item', timeout=5000)
            except Exception:
                console.print("[yellow]⚠️  No se detectaron tarjetas de oferta.[/yellow]")
                return []

        _scroll(self.page, veces=2)

        # ── Extraer tarjetas ──
        tarjetas = self.page.locator('a.gb-results-list__item').all()

        console.print(f"[dim]  Encontré {len(tarjetas)} enlaces de trabajo potenciales.[/dim]")

        ids_vistos = set()

        for tarjeta in tarjetas:
            try:
                href = tarjeta.get_attribute("href") or ""
                if not href or not any(x in href for x in ["/jobs/", "/empleos/"]):
                    continue
                # URL absoluta
                url_oferta = href if href.startswith("http") else f"{BASE_URL}{href}"

                # ID = el último segmento de la URL (el slug)
                partes = href.strip("/").split("/")
                identificador = partes[-1]
                if not identificador or identificador in ("jobs", "empleos", "search", ""):
                    console.print(f"[dim]    SKIPPED (id): {identificador}[/dim]")
                    continue
                
                oferta_id = identificador
                if oferta_id in ids_vistos:
                    console.print(f"[dim]    SKIPPED (duplicate id): {oferta_id}[/dim]")
                    continue
                ids_vistos.add(oferta_id)
                
                # Título: buscamos de forma más amplia
                titulo_locator = tarjeta.locator('h3 strong, h4 strong, .gb-results-list__title strong').first
                titulo = titulo_locator.inner_text().strip() if titulo_locator.count() > 0 else ""
                if not titulo:
                    # Fallback: cualquier strong dentro de h3/h4 o la tarjeta
                    titulo = tarjeta.locator('strong').first.inner_text().strip()

                # Empresa: el segundo strong o el que tenga el nombre de la empresa
                empresa_locator = tarjeta.locator('.gb-results-list__info strong, strong').all()
                empresa = "Empresa desconocida"
                if len(empresa_locator) >= 2:
                    empresa = empresa_locator[1].inner_text().strip()
                elif len(empresa_locator) == 1:
                    # Si solo hay uno, puede que no hayamos capturado el título bien
                    empresa = empresa_locator[0].inner_text().strip()

                ofertas.append({
                    "id": oferta_id,
                    "titulo": titulo or "Oferta sin título",
                    "empresa": empresa,
                    "url": url_oferta,
                })
            except Exception as e:
                console.print(f"[dim]  ⚠️  Error al procesar tarjeta: {e}[/dim]")
                continue

        console.print(f"[dim]  → {len(ofertas)} ofertas extraídas para procesar.[/dim]")
        _pausa(1, 2)
        return ofertas

    # ─────────────────────────────────────────────────────────────────
    #  OBTENER DETALLE
    # ─────────────────────────────────────────────────────────────────

    def obtener_detalle_oferta(self, url: str) -> dict:
        """Extrae el detalle de una oferta: título, empresa, descripción y si tiene botón 'Apply now'."""
        if self.page.url.split("?")[0] != url.split("?")[0]:
            self.page.goto(url, timeout=60000)
            _pausa(2, 4)

        detalle = {
            "titulo": "Sin título",
            "empresa": "Empresa desconocida",
            "descripcion": "",
            "puede_postular": False,
            "ya_postulado": False,
        }

        try:
            # Título
            for sel in ["h1", "h2", ".gb-job__title"]:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    txt = el.inner_text().strip()
                    if txt and len(txt) > 2:
                        detalle["titulo"] = txt
                        break

            # Empresa: link a página de empresa
            for sel in ["a[href*='/companies/']", ".gb-company-name", "h2 a"]:
                el = self.page.locator(sel).first
                if el.count() > 0:
                    txt = el.inner_text().strip().split("\n")[0]
                    if txt:
                        detalle["empresa"] = txt
                        break

            # Descripción (se extrae solo el texto, sin modificar el DOM)
            try:
                page_text = self.page.evaluate("""
                    () => {
                        // Extraer texto de forma no destructiva (sin eliminar elementos del DOM)
                        const selectors = [
                            '.gb-job__description',
                            '.gb-stack',
                            'article',
                            'main',
                            '#main-content',
                            '.gb-container'
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.innerText && el.innerText.length > 100) {
                                return el.innerText;
                            }
                        }
                        return document.body ? document.body.innerText : '';
                    }
                """).strip()
                if page_text and len(page_text) > 100:
                    detalle["descripcion"] = page_text[:12000]
            except Exception:
                body = self.page.query_selector("body")
                if body:
                    detalle["descripcion"] = body.inner_text()[:10000]

            # ¿Ya postulé? — aparece badge o texto especial
            ya_sels = [
                '.gb-applied-badge',
                'text="You already applied"',
                'text="Ya postulaste"',
                'button:has-text("Applied")',
            ]
            for sel in ya_sels:
                if self.page.locator(sel).count() > 0:
                    detalle["ya_postulado"] = True
                    break

            # ¿Hay botón "Apply now"?
            if not detalle["ya_postulado"]:
                # Incluir texto en español para detección correcta
                btn = self.page.locator(
                    '#apply_bottom_short, #apply_bottom, #apply_top, '
                    'a[href*="/applications/new"], '
                    'a:has-text("Apply now"), a:has-text("Apply"), '
                    'a:has-text("Postula"), a:has-text("Postular"), '
                    'a:has-text("Tienes una postulación por enviar"), '
                    '.gb-btn:has-text("Apply"), .gb-btn:has-text("Postula")'
                ).first
                if btn.count() > 0:
                    detalle["puede_postular"] = True

        except Exception as e:
            console.print(f"[dim]  ⚠️  Error extrayendo detalle: {e}[/dim]")

        return detalle

    # ─────────────────────────────────────────────────────────────────
    #  POSTULAR OFERTA  (flujo multi-paso de Get on Board)
    # ─────────────────────────────────────────────────────────────────

    def postular_oferta(self, oferta: dict, detalle: dict, modo_revision: bool = True) -> str:
        oferta_id  = oferta.get("id", "")
        titulo     = oferta.get("titulo", "")
        empresa    = oferta.get("empresa", "")
        url        = oferta.get("url", "")

        if ya_postule(oferta_id):
            console.print(f"[dim]  ⏭  Oferta {oferta_id} ya registrada.[/dim]")
            return "duplicado"

        if detalle.get("ya_postulado"):
            console.print("[dim]  ⏭  La oferta ya figura como postulada en Get on Board.[/dim]")
            registrar_postulacion(oferta_id, titulo, empresa, url, "duplicado", "")
            return "duplicado"

        # console.print(Panel.fit(
        #     f"[bold yellow]💼 {titulo}[/bold yellow]\n[cyan]🏢 {empresa}[/cyan]\n[dim]🔗 {url}[/dim]",
        #     title="[bold white]GET ON BOARD — POSTULANDO[/bold white]",
        #     border_style="bright_blue"
        # ))

        descripcion = detalle.get("descripcion", "")

        # ── Modo revisión: resumen IA antes de proceder ──
        if modo_revision:
            resumen = detalle.get("resumen_ia", "")
            # if not resumen:
            #     try:
            #         resumen = resumir_oferta(descripcion)
            #         detalle["resumen_ia"] = resumen
            #     except Exception:
            #         resumen = "(sin resumen disponible)"

            # console.print(Panel(
            #     f"[italic dim]{resumen}[/italic dim]",
            #     title="[bold cyan]📋 Resumen IA[/bold cyan]",
            #     border_style="cyan", padding=(0, 1)
            # ))
            # Eliminamos el input() redundante aquí, ya que el paso final de Submit pedirá confirmación definitiva.
            _pausa(0.5, 1)

        # ─── PASO 1: ir a la página del trabajo y clicar "Apply now" ───
        try:
            url_con_locale = f"{url}?locale=es" if "?" not in url else f"{url}&locale=es"
            if self.page.url.split("?")[0] != url.split("?")[0]:
                self.page.goto(url_con_locale, timeout=60000)
                _pausa(2, 3)

            # Verificar de nuevo si ya postulé
            for sel in ['.gb-applied-badge', 'text="You already applied"', 'text="Ya postulaste"']:
                if self.page.locator(sel).count() > 0:
                    registrar_postulacion(oferta_id, titulo, empresa, url, "duplicado", "")
                    return "duplicado"

            # Reintento de clic en Apply si la página no cambia
            ok_apply = False
            for intento_a in range(3):
                btn_apply = self.page.locator(
                    '#apply_bottom_short, #apply_bottom, #apply_top, '
                    'a[href*="/applications/new"], '
                    'a:has-text("Apply now"), a:has-text("Apply"), '
                    'a:has-text("Postula"), a:has-text("Postular"), '
                    'a:has-text("Tienes una postulación por enviar"), '
                    '.gb-btn:has-text("Apply"), .gb-btn:has-text("Postula")'
                ).first

                if btn_apply.count() > 0:
                    console.print(f"[dim]  Intentando clic en 'Postular' (intento {intento_a+1})...[/dim]")
                    btn_apply.scroll_into_view_if_needed()
                    _pausa(0.5, 1)
                    btn_apply.click(force=True)
                    _pausa(2, 4)
                    
                    if "/applications/" in self.page.url or "step=" in self.page.url:
                        ok_apply = True
                        break
                else:
                    if "/applications/" in self.page.url or "step=" in self.page.url:
                        ok_apply = True
                        break
                    _pausa(1, 2)

            if not ok_apply:
                console.print("[red]❌ No se pudo entrar al formulario de postulación.[/red]")
                registrar_postulacion(oferta_id, titulo, empresa, url, "error_boton", "")
                return "error_boton"

            # Asegurar español para los pasos iniciales, pero permitir inglés si es requerido por la oferta
            if "locale=es" not in self.page.url and "step=" in self.page.url:
                new_url = self.page.url
                char = "&" if "?" in new_url else "?"
                self.page.goto(f"{new_url}{char}locale=es")
            
            _pausa(1, 2)
            console.print(f"[dim]  → Formulario abierto: {self.page.url}[/dim]")

        except Exception as e:
            console.print(f"[red]❌ Error al iniciar postulación: {e}[/red]")
            registrar_postulacion(oferta_id, titulo, empresa, url, "error", "")
            return "error"

        # ─── PASOS 2-4: rellenar el formulario multi-paso ───
        try:
            estado = self._rellenar_formulario_aplicacion(descripcion, titulo, empresa)
        except Exception as e:
            console.print(f"[red]❌ Error en formulario: {e}[/red]")
            estado = "error"

        # Si el estado es "error_validacion", intentamos una vez más regresando al paso anterior o recargando
        if estado == "error_validacion":
            console.print("[yellow]⚠️  Detectado error de validación. Intentando corregir...[/yellow]")
            _pausa(2, 3)
            try:
                estado = self._rellenar_formulario_aplicacion(descripcion, titulo, empresa)
            except Exception:
                pass

        registrar_postulacion(oferta_id, titulo, empresa, url, estado, "")
        return estado

    # ─────────────────────────────────────────────────────────────────
    #  HELPER: navegar los pasos del formulario de postulación
    # ─────────────────────────────────────────────────────────────────

    def _rellenar_formulario_aplicacion(self, descripcion: str, titulo: str, empresa: str) -> str:
        """
        Navega por los pasos del formulario multi-paso de Get on Board.

        Flujo real:
        1. /applications/new     → Vista previa inicial, clic #submit-btn (Siguiente)
        2. ?step=experience      → Solo clic #submit-btn (Siguiente)
        3. ?step=basic           → Salario + razón + checkbox → clic #submit-btn (Siguiente)
        4. ?step=questions       → Preguntas adicionales → clic #submit-btn (Siguiente)
        5. /applications/ID (sin step=) → Botón "Enviar postulación ahora" → confirmación
        """
        max_pasos = 10
        pasos_completados = 0

        while pasos_completados < max_pasos:
            current_url = self.page.url
            console.print(f"[dim]  Formulario paso {pasos_completados+1}: {current_url}[/dim]")
            _pausa(1, 2)

            # ── ¿Ya se completó? Verificar confirmación ──
            if self._es_confirmacion_exitosa():
                console.print("[green]✅ Postulación enviada exitosamente en Get on Board[/green]")
                return "enviada"

            # ── Paso inicial: /applications/new ──
            if "/applications/new" in current_url:
                console.print("[dim]  → Paso: Inicio (vista previa del perfil) → clic Siguiente[/dim]")
                self._clic_next()

            # ── Paso experience ──
            elif "step=experience" in current_url:
                console.print("[dim]  → Paso: Experiencia → clic Siguiente[/dim]")
                self._paso_experience()

            # ── Paso basic ──
            elif "step=basic" in current_url:
                console.print("[dim]  → Paso: Información básica[/dim]")
                self._paso_basic(descripcion, titulo, empresa)

            # ── Paso questions ──
            elif "step=questions" in current_url:
                console.print("[dim]  → Paso: Preguntas[/dim]")
                self._paso_questions(descripcion)

            # ── Paso final: preview/send (URL base sin step=) ──
            elif "/applications/" in current_url and "step=" not in current_url and "/new" not in current_url and "edit" not in current_url:
                console.print("[dim]  → Paso: Preview / Envío final[/dim]")
                resultado = self._paso_preview_submit()
                return "enviada" if resultado else "error_confirmacion"

            # ── Paso desconocido: avanzar con Next ──
            else:
                console.print(f"[yellow]⚠️  Paso desconocido: {current_url}[/yellow]")
                if not self._clic_next():
                    console.print("[red]❌ No se encontró botón para avanzar.[/red]")
                    return "error_formulario"

            pasos_completados += 1
            _pausa(2, 4)

            # Verificar si avanzó
            nueva_url = self.page.url
            if nueva_url == current_url:
                console.print(f"[yellow]⚠️  La URL no cambió en {current_url}. Posible error de validación.[/yellow]")
                # Buscar mensajes de error específicos
                errores = self.page.locator('.form-error, .error-message, .alert-error, [class*="error"]:visible').all()
                if errores:
                    for err in errores:
                        txt = err.inner_text().strip()
                        if txt:
                            console.print(f"[red]  🛑 Error detectado: {txt[:250]}[/red]")
                
                # Si estamos trabados, intentamos rellenar los campos de nuevo en este paso
                # pero retornamos error_validacion para que el llamador decida si reintenta
                return "error_validacion"

        console.print("[yellow]⚠️  Se alcanzó el límite de pasos.[/yellow]")
        return "error_formulario"

    def _paso_experience(self):
        """Paso 'Experience': simplemente avanza con Next (el CV ya está cargado en el perfil)."""
        _pausa(1, 2)
        self._clic_next()

    def _paso_basic(self, descripcion: str, titulo: str, empresa: str):
        """
        Paso 'Basic Information':
        - Rellena salario esperado (campo numérico en USD)
        - Rellena razón de postulación (textarea, 50-1000 chars)
        - Marca checkbox de permiso laboral si existe
        - Hace clic en Next
        """
        _pausa(1, 2)

        # Salario esperado (número en USD)
        sal_input = self.page.locator(
            '#job_application_expected_salary, '
            'input[name="job_application[expected_salary]"], '
            'input[type="number"][id*="salary"]'
        ).first
        if sal_input.count() > 0:
            try:
                perfil = cargar_perfil()
                renta_clp = int(str(perfil.get("preferencias", {}).get("renta_esperada", "800000")).replace(".", "").replace(",", ""))
                salario_usd_raw = renta_clp / 970
                # Redondear al múltiplo de 50 más cercano (Get on Board solo acepta múltiplos de 50)
                salario_usd = max(300, round(salario_usd_raw / 50) * 50)
            except Exception:
                salario_usd = 800
            sal_input.scroll_into_view_if_needed()
            sal_input.click()
            sal_input.fill(str(salario_usd))
            console.print(f"[dim]  → Salario esperado: {salario_usd} USD[/dim]")
            _pausa(0.3, 0.7)

        # Razón de postulación
        razon_input = self.page.locator(
            '#reason-to-apply, '
            'textarea[name="job_application[reason_to_apply]"], '
            'textarea[id*="reason"]'
        ).first
        if razon_input.count() > 0:
            console.print("[dim]  → Analizando requisitos para la razón de postulación...[/dim]")
            
            # Detectar si se requiere inglés
            idioma_requerido = "español"
            page_content = self.page.content().lower()
            if "escrita en inglés" in page_content or "written in english" in page_content or "in english" in page_content:
                idioma_requerido = "inglés"
                console.print("[yellow]  🌐 Detectado requisito de idioma INGLÉS para la razón.[/yellow]")
            
            try:
                prompt = (
                    f"¿Por qué te interesa trabajar en {empresa} como {titulo}? "
                    f"Responde en {idioma_requerido}, entre 150 y 600 caracteres. Sé específico y profesional. "
                    "Habla sobre tu pasión por la tecnología y cómo encajas en el puesto."
                )
                razon_texto = responder_pregunta(prompt, descripcion)
                
                # Validar longitud mínima
                if len(razon_texto) < 60:
                    razon_texto = responder_pregunta(f"{prompt} (ASEGÚRATE DE QUE TENGA AL MENOS 100 CARACTERES)", descripcion)
                
                razon_texto = razon_texto[:1000]
            except Exception:
                if idioma_requerido == "inglés":
                    razon_texto = (
                        f"I am very excited about the opportunity to join {empresa} as a {titulo}. "
                        "I have the skills and experience necessary to contribute effectively to your team and I am eager to grow within the company."
                    )
                else:
                    razon_texto = (
                        f"Me entusiasma la oportunidad de unirme a {empresa} como {titulo}. "
                        "Cuento con las habilidades y experiencia necesarias para aportar al equipo y estoy ansioso por crecer con ustedes."
                    )
            
            razon_input.scroll_into_view_if_needed()
            razon_input.click()
            razon_input.fill("")
            razon_input.type(razon_texto, delay=random.randint(5, 20))
            _pausa(0.5, 1)
            console.print(f"[dim]  → Razón escrita en {idioma_requerido} ({len(razon_texto)} chars)[/dim]")

        # Checkbox de permiso laboral / residencia
        checkbox = self.page.locator(
            '#confirm_residency, '
            'input[type="checkbox"][id*="resid"], '
            'input[type="checkbox"][id*="legal"], '
            'input[type="checkbox"][id*="work"]'
        ).first
        if checkbox.count() > 0 and not checkbox.is_checked():
            checkbox.scroll_into_view_if_needed()
            checkbox.click()
            console.print("[dim]  → Checkbox de residencia marcado[/dim]")
            _pausa(0.3, 0.5)

        # Otros checkboxes requeridos
        checkboxes = self.page.locator('input[type="checkbox"][required]').all()
        for cb in checkboxes:
            try:
                if not cb.is_checked():
                    cb.click()
                    _pausa(0.2, 0.4)
            except Exception:
                pass

        self._clic_next()

    def _paso_questions(self, descripcion: str):
        """
        Paso 'Questions': responde preguntas adicionales del empleador con IA.
        """
        _pausa(1, 2)

        # Responder textareas vacíos
        textareas = self.page.locator('textarea:visible').all()
        for ta in textareas:
            try:
                val = ta.input_value()
                if not val.strip():
                    ta_id = ta.get_attribute("id") or ""
                    label_text = ""
                    if ta_id:
                        lbl = self.page.locator(f'label[for="{ta_id}"]').first
                        if lbl.count() > 0:
                            label_text = lbl.inner_text().strip()
                    respuesta = responder_pregunta(label_text or "Pregunta del empleador", descripcion)
                    respuesta = respuesta[:1000]
                    ta.scroll_into_view_if_needed()
                    ta.click()
                    ta.fill("")
                    for char in respuesta:
                        ta.type(char, delay=random.randint(10, 40))
                    _pausa(0.3, 0.7)
            except Exception:
                pass

        # Responder inputs de texto/número vacíos
        text_inputs = self.page.locator('input[type="text"]:visible, input[type="number"]:visible').all()
        for inp in text_inputs:
            try:
                val = inp.input_value()
                if not val.strip():
                    inp_id = inp.get_attribute("id") or ""
                    label_text = ""
                    if inp_id:
                        lbl = self.page.locator(f'label[for="{inp_id}"]').first
                        if lbl.count() > 0:
                            label_text = lbl.inner_text().strip()
                    inp_type = inp.get_attribute("type") or "text"
                    if inp_type == "number":
                        respuesta = responder_pregunta(f"Responde SOLO con un número: {label_text}", descripcion)
                        nums = re.findall(r'\d+', respuesta)
                        respuesta = nums[0] if nums else "0"
                    else:
                        respuesta = responder_pregunta(label_text or "Responde brevemente", descripcion)[:200]
                    inp.scroll_into_view_if_needed()
                    inp.click()
                    inp.fill(str(respuesta))
                    _pausa(0.2, 0.5)
            except Exception:
                pass

        # Selects: elegir primera opción no vacía
        selects = self.page.locator('select:visible').all()
        for sel_el in selects:
            try:
                current_val = sel_el.input_value()
                if not current_val:
                    options = sel_el.locator('option').all()
                    for opt in options:
                        opt_val = opt.get_attribute("value") or ""
                        if opt_val and opt_val.strip():
                            sel_el.select_option(value=opt_val)
                            _pausa(0.2, 0.4)
                            break
            except Exception:
                pass

        # Checkboxes requeridos
        checkboxes = self.page.locator('input[type="checkbox"][required]:visible').all()
        for cb in checkboxes:
            try:
                if not cb.is_checked():
                    cb.click()
                    _pausa(0.2, 0.4)
            except Exception:
                pass

        self._clic_next()

    def _paso_preview_submit(self) -> bool:
        """Paso final 'Preview': hace clic en el botón de envío definitivo."""
        _pausa(1, 2)

        submit_sel = (
            '#send-application-btn-1, '
            'input[value*="Enviar postulación ahora"], '
            'input[data-label="job-application-send-now"], '
            'input[id*="send-application-btn"], '
            'button:has-text("Enviar postulación ahora"), '
            'button:has-text("Submit application"), '
            'button:has-text("Submit"), '
            'input[type="submit"][value*="Submit"], '
            'a:has-text("Send application"), '
            'a.gb-btn:has-text("Send"), '
            'a.gb-btn:has-text("Submit"), '
            'button:has-text("Enviar postulación"), '
            'button:has-text("Enviar"), '
            '#submit-btn'
        )
        
        # Intentar esperar a que el botón sea visible (especialmente si es un modal)
        try:
            self.page.wait_for_selector('input[value*="Enviar"], #send-application-btn-1, button:has-text("Enviar")', timeout=5000)
        except Exception:
            pass

        btn_submit = self.page.locator(submit_sel).first

        if btn_submit.count() > 0:
            # Asegurarse de que el botón sea cliqueable (no disabled)
            btn_submit.scroll_into_view_if_needed()
            _pausa(0.5, 1)
            
            # El usuario pidió autorización para el envío final de formularios
            while True:
                confirmar_envio = input("  🚀 ¿Enviar postulación definitiva a Get on Board? [s = Sí / n = No]: ").strip().lower()
                if confirmar_envio in ['s', 'n']:
                    break
                console.print(f"  [red]⚠️ Te equivocaste, ingresa 's' o 'n' (escribiste: '{confirmar_envio}').[/red]")

            if confirmar_envio == "s":
                try:
                    # Forzar el clic si es necesario (a veces hay overlays invisibles en modales)
                    btn_submit.click(force=True)
                except Exception:
                    # Fallback por si acaso
                    self.page.evaluate('''(sel) => {
                        const btn = document.querySelector(sel);
                        if (btn) btn.click();
                    }''', submit_sel.split(',')[0]) # Intentar con el primer selector
                
                _pausa(4, 6)
                return self._es_confirmacion_exitosa()
            else:
                console.print("[yellow]  ⏭  Postulación detenida por el usuario antes de enviar.[/yellow]")
                return False
        else:
            if self._clic_next():
                _pausa(3, 5)
                return self._es_confirmacion_exitosa()
        return False

    def _clic_next(self) -> bool:
        """Hace clic en el botón 'Next', 'Siguiente' o 'Submit' del paso actual con reintentos."""
        next_sel = (
            '#submit-btn, '
            'button[type="submit"]:has-text("Next"), '
            'button[type="submit"]:has-text("Siguiente"), '
            'button[type="submit"]:has-text("Save"), '
            'button[type="submit"]:has-text("Guardar"), '
            'button[type="submit"]:has-text("Continue"), '
            'button[type="submit"]:has-text("Continuar"), '
            'button:has-text("Siguiente"), '
            'button:has-text("Next"), '
            'a.gb-btn:has-text("Continuar"), '
            'a.gb-btn:has-text("Completar"), '
            'a.gb-btn:has-text("Siguiente"), '
            'button[type="submit"]:visible, '
            'input[type="submit"]:visible'
        )
        
        url_antes = self.page.url
        for i in range(3):
            btn = self.page.locator(next_sel).first
            if btn.count() > 0:
                try:
                    btn.scroll_into_view_if_needed()
                    _pausa(0.5, 1)
                    btn.click(force=True, timeout=5000)
                    _pausa(2, 4)
                    
                    # Si el URL cambió o el botón ya no está, asumimos éxito
                    if self.page.url != url_antes or self.page.locator(next_sel).first.count() == 0:
                        return True
                except Exception:
                    pass
            _pausa(1, 2)
            
        return False

    def _es_confirmacion_exitosa(self) -> bool:
        """Verifica si estamos en la página de confirmación de postulación exitosa."""
        url = self.page.url
        confirmacion_sels = [
            '.gb-applied-badge',
            'text="Application sent"',
            'text="Postulación enviada"',
            '[class*="success"]',
            'text="Thank you"',
            '.alert-success',
        ]
        # Si no tiene /edit ni step=... y tiene /applications/ → probablemente es preview o confirmación
        if "/applications/" in url and "edit" not in url and "step=" not in url:
            for sel in confirmacion_sels:
                if self.page.locator(sel).count() > 0:
                    return True
        return False
