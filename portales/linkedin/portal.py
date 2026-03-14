import os
import random
import time
from playwright.sync_api import Page, BrowserContext
from rich.console import Console
from rich.panel import Panel

from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD, SESSION_PATH, CV_PATH, cargar_perfil
from ai_responder import responder_pregunta, resumir_oferta, elegir_opcion_select
from database import ya_postule, registrar_postulacion
from portales.base import PortalBase

console = Console()

def _pausa(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))


class LinkedinPortal(PortalBase):
    
    def __init__(self, page: Page, context: BrowserContext):
        super().__init__(page, context)
        self.nombre = "LinkedIn"
        self.base_url = "https://www.linkedin.com"
        self.login_url = f"{self.base_url}/login"
        self.ofertas_url = f"{self.base_url}/jobs/search"

    def login(self) -> bool:
        """Inicia sesión en LinkedIn."""
        console.print(f"[cyan]Navegando a {self.login_url}[/cyan]")
        try:
            self.page.goto(self.login_url, timeout=60000)
            _pausa(2, 4)
        except Exception as e:
            if "ERR_INTERNET_DISCONNECTED" in str(e):
                console.print("[bold red]❌ No hay conexión a Internet. Verifica tu red.[/bold red]")
            else:
                console.print(f"[red]❌ Error de red al intentar cargar LinkedIn: {e}[/red]")
            return False

        if "feed" in self.page.url or "Mynetwork" in self.page.url:
            print("✅ Sesión activa detectada (LinkedIn)")
            return True

        try:
            # Selectores según el HTML proporcionado por el usuario
            email_sel = '#username'
            pass_sel  = '#password'

            self.page.wait_for_selector(email_sel, timeout=15000)
            
            email_loc = self.page.locator(email_sel)
            box_email = email_loc.bounding_box()
            if box_email:
                self.page.mouse.move(box_email["x"] + box_email["width"] / 2, box_email["y"] + box_email["height"] / 2, steps=10)
                _pausa(0.2, 0.5)
            email_loc.click()
            _pausa(0.5, 1.0)
            # Tipeamos de forma secuencial y con retraso variable para imitar a un humano
            email_loc.press_sequentially(LINKEDIN_EMAIL.strip(), delay=random.randint(150, 400))
            _pausa(1.0, 2.5)
            
            pass_loc = self.page.locator(pass_sel)
            box_pass = pass_loc.bounding_box()
            if box_pass:
                self.page.mouse.move(box_pass["x"] + box_pass["width"] / 2, box_pass["y"] + box_pass["height"] / 2, steps=15)
                _pausa(0.2, 0.5)
            pass_loc.click()
            _pausa(0.5, 1.5)
            pass_loc.press_sequentially(LINKEDIN_PASSWORD.strip(), delay=random.randint(150, 400))
            _pausa(1.0, 2.5)
            
            # Botón de submit basado en el HTML proporcionado
            btn_login = self.page.locator('button[type="submit"][data-litms-control-urn="login-submit"], button[type="submit"]').first
            
            try:
                box = btn_login.bounding_box()
                if box:
                    self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=10)
                    _pausa(0.3, 0.8)
            except Exception:
                pass

            btn_login.click(delay=random.randint(50, 150))

            # Esperar a ver si cambia de página o aparece algún elemento de login exitoso
            try:
                self.page.wait_for_selector('.form__label--error, #error-for-password', timeout=5000)
                print("❌ Login fallido — Credenciales inválidas o captcha.")
                return False
            except:
                pass # No hubo error visible rápido

            _pausa(3, 6)

            # Comprobar estado final
            if "login" not in self.page.url and "checkpoint" not in self.page.url:
                print("✅ Login exitoso en LinkedIn")
                self._guardar_sesion()
                return True
            elif "checkpoint" in self.page.url:
                print("⚠️ LinkedIn solicita verificación adicional (Captcha/2FA). Por favor, resuelve manualmente en la ventana del navegador.")
                # Damos tiempo al usuario para resolver el desafío
                self.page.wait_for_url("**/feed/**", timeout=120000)
                print("✅ Desafío resuelto. Login exitoso.")
                self._guardar_sesion()
                return True
            else:
                print(f"❌ Login fallido — la URL no cambió: {self.page.url}")
                return False
        except Exception as e:
            print(f"❌ Error en login LinkedIn: {e}")
            return False

    def aplicar_filtros_avanzados(self, carrera: str, region: str):
        """Navega a la sección de empleos y aplica filtros dinámicos."""
        cargo_search = carrera or "ingeniero informatico"
        ubicacion_search = region or "Santiago, Chile"
        
        console.print(f"[cyan]Aplicando filtros en LinkedIn: {cargo_search} | {ubicacion_search}[/cyan]")
        
        # 1. Intentar navegación directa para mayor fiabilidad
        # (A veces los inputs de búsqueda no cargan rápido o están ocultos)
        # f_E=1%2C2%2C3 (Prácticas, Sin experiencia, Algo de responsabilidad), f_AL=true (Solicitud Sencilla / Easy Apply)
        search_url = f"{self.base_url}/jobs/search/?keywords={cargo_search.replace(' ', '%20')}&location={ubicacion_search.replace(' ', '%20')}&f_E=1%2C2%2C3&f_AL=true"
        
        try:
            console.print(f"[dim]Navegando directamente a la búsqueda...[/dim]")
            self.page.goto(search_url, timeout=45000)
            self.page.wait_for_load_state("domcontentloaded")
            _pausa(3, 5)
            
            # Verificar si estamos en la página de resultados
            if "jobs/search" in self.page.url:
                console.print("[green]✅ Búsqueda cargada vía URL directa[/green]")
                return

        except Exception as e:
            console.print(f"[dim]Error en navegación directa, intentando vía interfaz: {e}[/dim]")

        # 2. Fallback: Navegar a Empleos y llenar los campos manualmente
        try:
            self.page.goto(f"{self.base_url}/jobs/", timeout=30000)
            _pausa(2, 4)
            
            # Selectores de búsqueda (LinkedIn cambia estos frecuentemente)
            input_cargo = self.page.locator('input.jobs-search-box__keyboard-text-input[aria-label*="Cargo"], input.jobs-search-box__text-input[aria-label*="Cargo"], input[id*="jobs-search-box-keyword"]').first
            input_ubicacion = self.page.locator('input.jobs-search-box__keyboard-text-input[aria-label*="Ciudad"], input.jobs-search-box__text-input[aria-label*="Ciudad"], input[id*="jobs-search-box-location"]').first

            if input_cargo.count() > 0:
                input_cargo.click()
                input_cargo.fill("")
                input_cargo.press_sequentially(cargo_search, delay=random.randint(80, 250))
                _pausa(0.5, 1.0)

            if input_ubicacion.count() > 0:
                input_ubicacion.click()
                input_ubicacion.fill("")
                input_ubicacion.press_sequentially(ubicacion_search, delay=random.randint(80, 250))
                _pausa(1.0, 2.0)
                input_ubicacion.press("Enter")
            else:
                # Si no hay bucket de ubicación, talvez el de cargo ya tiene foco
                input_cargo.press("Enter")

            _pausa(4, 6)
            
            # Clicar filtros de Nivel de Experiencia según petición explícita
            try:
                console.print("[dim]Aplicando filtros de Nivel de Experiencia vía clic...[/dim]")
                btn_exp = self.page.locator('button:has-text("Nivel de experiencia"), button[aria-label*="Nivel de experiencia"]').first
                if btn_exp.count() > 0 and btn_exp.is_visible():
                    btn_exp.click()
                    _pausa(1, 2)
                    
                    opciones = ["Prácticas", "Sin experiencia", "Algo de responsabilidad"]
                    for opcion in opciones:
                        lbl_opcion = self.page.locator(f'label:has-text("{opcion}")').first
                        if lbl_opcion.count() > 0 and lbl_opcion.is_visible():
                            # Hacer clic en el label
                            lbl_opcion.click()
                            _pausa(0.5, 1.5)
                    
                    btn_mostrar = self.page.locator('button:has-text("Mostrar resultados"), button:has-text("Show results")').last
                    if btn_mostrar.count() > 0 and btn_mostrar.is_visible():
                        btn_mostrar.click()
                        _pausa(2, 4)
                        console.print("[green]✅ Filtros de experiencia aplicados vía clic[/green]")
            except Exception as e:
                console.print(f"[dim]No se pudieron aplicar los clics de experiencia: {e}[/dim]")

            console.print("[green]✅ Búsqueda enviada vía interfaz[/green]")

        except Exception as e:
            console.print(f"[red]❌ No se pudieron aplicar los filtros: {e}[/red]")

    def obtener_ofertas(self, paginas: int = 3, num_pagina_actual: int = 1) -> list[dict]:
        """Obtiene una lista de ofertas de la página actual de resultados de LinkedIn."""
        console.print(f"[cyan]Obteniendo ofertas de la página {num_pagina_actual}...[/cyan]")
        ofertas_extraidas = []
        
        try:
             # Esperar a que la lista de resultados cargue
             selectores_lista = [
                 'ul.scaffold-layout__list-container',
                 '.jobs-search-results-list',
                 '.scaffold-layout__list',
                 '[data-job-id]'
             ]
             
             lista_encontrada = False
             for sel in selectores_lista:
                 if self.wait_for_selector_safe(sel, timeout=7000):
                     lista_encontrada = True
                     break
             
             if not lista_encontrada:
                 if self.page.locator('a[href*="/jobs/view/"]').count() == 0:
                     console.print("[yellow]⚠️ No se detectó la lista de empleos.[/yellow]")
                     return []

             _pausa(1, 2)
             
             # En LinkedIn hay que scrollear el panel izquierdo para que carguen todos (suelen ser 25)
             # Buscamos el div que tiene el scroll
             paneles = self.page.locator('.jobs-search-results-list, .scaffold-layout__list, .jobs-search-results-container').all()
             for panel in paneles:
                 try:
                     for _ in range(4):
                        panel.evaluate("node => node.scrollTop += 1000")
                        _pausa(0.5, 1.0)
                 except: pass

             # Seleccionar los elementos de lista que representan las ofertas
             tarjetas = self.page.locator('li[data-occludable-job-id], li.jobs-search-results__list-item, .job-card-container').all()
             
             console.print(f"[dim]Se encontraron {len(tarjetas)} tarjetas potenciales.[/dim]")

             for tarjeta in tarjetas:
                 try:
                      # Extraer información de la tarjeta
                      btn_titulo = tarjeta.locator('a.job-card-list__title--link, a.job-card-container__link, [data-control-name="job_card_click"]').first
                      
                      if btn_titulo.count() == 0: continue

                      titulo = btn_titulo.inner_text().strip()
                      
                      # Detectar si ya postulamos según la UI de LinkedIn
                      ya_postulado_ui = False
                      status_loc = tarjeta.locator('.job-card-container__footer-item--status, .job-card-list__footer-item, .job-card-container__footer-item').first
                      if status_loc.count() > 0:
                          status_text = status_loc.inner_text().lower()
                          if any(x in status_text for x in ["postulado", "applied", "solicitud enviada"]):
                              ya_postulado_ui = True
                              console.print(f"  [dim]⏭  Omitiendo '{titulo}' (ya aparece como Postulado en LinkedIn).[/dim]")

                      if ya_postulado_ui:
                          continue

                      url_raw = btn_titulo.get_attribute("href") or ""
                      url_oferta = url_raw.split('?')[0]
                      if url_oferta.startswith('/'):
                          url_oferta = f"https://www.linkedin.com{url_oferta}"

                      empresa_loc = tarjeta.locator('.job-card-container__primary-description, .job-card-container__company-name, .artdeco-entity-lockup__subtitle').first
                      empresa = empresa_loc.inner_text().strip() if empresa_loc.count() > 0 else "Empresa Desconocida"
                      
                      oferta_id = tarjeta.get_attribute("data-job-id") or tarjeta.get_attribute("data-occludable-job-id")
                      if not oferta_id:
                          import re
                          match = re.search(r'/view/(\d+)', url_oferta)
                          oferta_id = match.group(1) if match else None
                          
                      if not oferta_id:
                          import hashlib
                          oferta_id = f"hash-{hashlib.md5(url_oferta.encode()).hexdigest()[:10]}"

                      ofertas_extraidas.append({
                           "id": oferta_id,
                           "titulo": titulo,
                           "url": url_oferta,
                           "empresa": empresa
                      })
                 except Exception as e:
                      continue
             
             # Eliminar duplicados en caso de que un elemento sea mapeado dos veces por los selectores
             ofertas_unicas = []
             ids_vistos = set()
             for o in ofertas_extraidas:
                 if o["id"] not in ids_vistos:
                     ids_vistos.add(o["id"])
                     ofertas_unicas.append(o)
             ofertas_extraidas = ofertas_unicas

             console.print(f"[green]✅ {len(ofertas_extraidas)} ofertas detectadas en esta página.[/green]")

             # Paginación simplificada (opcional por ahora, el usuario suele querer la primera)
             if num_pagina_actual < paginas and len(ofertas_extraidas) > 0:
                 try:
                      btn_next = self.page.locator(f'button[aria-label="Página {num_pagina_actual + 1}"], li[data-test-pagination-page-btn] button').all()
                      # Buscamos el exacto para la siguiente página
                      for b in btn_next:
                          if str(num_pagina_actual + 1) in b.inner_text():
                              b.click()
                              _pausa(3, 5)
                              break
                 except: pass
                      
        except Exception as e:
             console.print(f"[red]❌ Error al obtener ofertas en LinkedIn: {e}[/red]")
             
        return ofertas_extraidas

    def obtener_detalle_oferta(self, url: str) -> dict:
        """Navega a la oferta y comprueba si es 'Solicitud sencilla' (Easy Apply)."""
        # Si ya estamos en la URL, no navegamos de nuevo (main.py ya lo hace)
        if self.page.url.split('?')[0] != url.split('?')[0]:
            console.print(f"[cyan]Navegando al detalle: {url}[/cyan]")
            try:
                self.page.goto(url, timeout=45000)
                self.page.wait_for_load_state("domcontentloaded")
                _pausa(2, 4)
            except Exception as e:
                console.print(f"[dim]Error al navegar al detalle: {e}[/dim]")

        detalle = {
            "titulo": "Título Desconocido",
            "empresa": "Empresa Desconocida", 
            "descripcion": "",
            "tipo": "external", 
            "es_sencilla": False
        }
        
        try:
            # Extraer títulos y descripción para la IA en main.py
            selectors_titulo = [
                '.job-details-jobs-unified-top-card__job-title',
                'h2.jobs-unified-top-card__job-title',
                '.jobs-unified-top-card__job-title h1',
                'h1.t-24',
                'div[class*="job-title"] h1'
            ]
            for sel in selectors_titulo:
                tit_loc = self.page.locator(sel).first
                if tit_loc.count() > 0:
                    detalle["titulo"] = tit_loc.inner_text().strip()
                    break
            
            selectors_empresa = [
                '.job-details-jobs-unified-top-card__company-name',
                '.jobs-unified-top-card__company-name',
                'div[class*="company-name"] a',
                '.jobs-top-card__company-url',
                '.artdeco-entity-lockup__subtitle'
            ]
            for sel in selectors_empresa:
                emp_loc = self.page.locator(sel).first
                if emp_loc.count() > 0:
                    detalle["empresa"] = emp_loc.inner_text().strip().split('\n')[0]
                    break

            selectors_desc = [
                '#job-details',
                '.jobs-description__container',
                '.jobs-description-content__text',
                '.jobs-description',
                '.show-more-less-html__markup'
            ]
            for sel in selectors_desc:
                desc_loc = self.page.locator(sel).first
                if desc_loc.count() > 0:
                    detalle["descripcion"] = desc_loc.inner_text().strip()
                    break

            # Verificar si existe el botón/enlace de "Solicitud sencilla" (Easy Apply)
            # En LinkedIn NUEVO el botón es un <a> con aria-label="Solicitud sencilla"
            # En LinkedIn CLÁSICO es un <button>. Buscamos ambos.
            SELECTOR_EASY_APPLY = (
                'a[aria-label*="Solicitud sencilla"], '
                'a[aria-label*="Easy Apply"], '
                'a[data-view-name="job-apply-button"], '
                'button[aria-label*="Solicitud sencilla"], '
                'button[aria-label*="Easy Apply"], '
                'button:has-text("Solicitud sencilla"), '
                'button:has-text("Easy Apply")'
            )
            btn_sencilla = self.page.locator(SELECTOR_EASY_APPLY).first
            
            if btn_sencilla.count() > 0:
                texto_boton = (btn_sencilla.get_attribute("aria-label") or btn_sencilla.inner_text()).lower()
                if "sencilla" in texto_boton or "easy" in texto_boton:
                    # Guardar el href por si el flujo de apply es vía URL
                    apply_href = btn_sencilla.get_attribute("href") or ""
                    detalle["apply_href"] = apply_href
                    console.print("[green]✨ Esta oferta permite 'Solicitud sencilla'[/green]")
                    detalle["es_sencilla"] = True
                    detalle["tipo"] = "easy_apply"
                else:
                    console.print(f"[yellow]ℹ️ Botón encontrado pero no parece 'Sencilla': '{texto_boton}'[/yellow]")
            else:
                console.print("[yellow]ℹ️ Oferta externa o botón no encontrado.[/yellow]")

        except Exception as e:
            console.print(f"[dim]Error al extraer detalle: {e}[/dim]")
            
        return detalle
        
    def postular_oferta(self, oferta: dict, detalle: dict, modo_revision: bool = True) -> str:
        """Realiza el proceso de 'Solicitud Sencilla' de LinkedIn."""
        oferta_id = oferta.get("id", "")
        if ya_postule(oferta_id):
            console.print(f"[dim]⏭  Omitiendo {oferta_id} (ya postulado en DB).[/dim]")
            return "duplicado"

        if not detalle.get("es_sencilla"):
            return "external"

        console.print(f"[magenta]Iniciando postulación sencilla para: {oferta['titulo']}[/magenta]")
        
        try:
            # Botón / enlace principal (Solicitud sencilla / Easy Apply)
            # En LinkedIn nuevo es un <a>, en el clásico es un <button>
            SELECTOR_EASY_APPLY = (
                'a[aria-label*="Solicitud sencilla"], '
                'a[aria-label*="Easy Apply"], '
                'a[data-view-name="job-apply-button"], '
                'button[aria-label*="Solicitud sencilla"], '
                'button[aria-label*="Easy Apply"], '
                'button:has-text("Solicitud sencilla"), '
                'button:has-text("Easy Apply")'
            )
            btn_sencilla = self.page.locator(SELECTOR_EASY_APPLY).first
            if btn_sencilla.count() == 0:
                console.print("[red]❌ No se encontró el botón/enlace 'Solicitud sencilla'. Revisa si la oferta sigue siendo Easy Apply.[/red]")
                return "error_boton"
            
            # Si el botón es un <a> con href de flujo de apply, navegamos directamente
            apply_href = detalle.get("apply_href", "") or btn_sencilla.get_attribute("href") or ""
            if apply_href and "openSDUIApplyFlow" in apply_href:
                console.print("[dim]Navegando al flujo Easy Apply vía href...[/dim]")
                # Navegamos al href en la misma página
                full_href = apply_href if apply_href.startswith("http") else f"https://www.linkedin.com{apply_href}"
                self.page.goto(full_href, timeout=45000)
                self.page.wait_for_load_state("domcontentloaded")
            else:
                btn_sencilla.click()
            _pausa(2, 4)
            
            # Esperar a que aparezca el modal de postulación
            try:
                self.page.wait_for_selector(
                    '.jobs-easy-apply-modal, .artdeco-modal, [role="dialog"]',
                    timeout=10000
                )
            except:
                pass
            
            descripcion = detalle.get("descripcion", "")
            
            # Manejar el Modal (Siguiente, Siguiente, Revisar, Enviar)
            max_pasos = 12
            for paso in range(max_pasos):
                
                # 0. Rellenar campos inteligentemente antes de avanzar
                console.print(f"\n  [bold blue]── Paso {paso+1}: escaneando campos ──[/bold blue]")

                # Datos del perfil para autocompletar sin IA
                PERFIL_TELEFONO = "944399872"   # sin código de país
                PERFIL_EMAIL    = "jose.oporto.va@gmail.com"
                PERFIL_NOMBRE   = "José Oporto"
                RENTA_ESPERADA  = "300000"

                PALABRAS_TELEFONO = ["teléfono", "telefono", "phone", "móvil", "movil", "celular", "whatsapp"]
                PALABRAS_EMAIL    = ["email", "correo", "e-mail"]
                PALABRAS_NOMBRE   = ["nombre", "name", "apellido", "surname"]
                PALABRAS_RENTA    = ["renta", "salario", "sueldo", "salary", "expectativa", "remuneración", "remuneracion"]
                PALABRAS_ANOS     = ["años", "year", "meses", "month", "cuántos", "cuantos", "how many", "experiencia"]

                def tipo_campo(label_text: str) -> str:
                    ll = label_text.lower()
                    if any(k in ll for k in PALABRAS_TELEFONO): return "telefono"
                    if any(k in ll for k in PALABRAS_EMAIL):    return "email"
                    if any(k in ll for k in PALABRAS_NOMBRE):   return "nombre"
                    if any(k in ll for k in PALABRAS_RENTA):    return "renta"
                    if any(k in ll for k in PALABRAS_ANOS):     return "anos"
                    return "texto"

                campos_rellenados = []  # Para la revisión interactiva

                try:
                    # ── CV Upload ──
                    cv_upload = self.page.locator('input[type="file"]')
                    if cv_upload.count() > 0 and os.path.exists(CV_PATH):
                        console.print(f"  [magenta]📎 CV detectado → subiendo: {os.path.basename(CV_PATH)}[/magenta]")
                        try:
                            cv_upload.first.set_input_files(CV_PATH)
                            console.print("  [green]✅ CV subido[/green]")
                            _pausa(1, 2)
                        except Exception as e:
                            console.print(f"  [red]❌ Error CV: {e}[/red]")
                    elif cv_upload.count() > 0:
                        console.print(f"  [red]⚠️  CV requerido pero no encontrado en: {CV_PATH}[/red]")

                    # ── Contenedores de preguntas ──
                    contenedores = self.page.locator(
                        '.jobs-easy-apply-form-section__item, '
                        '.jobs-easy-apply-modal__content .fb-form-element, '
                        '.fb-dash-form-element'
                    ).all()

                    for container in contenedores:
                        if not container.is_visible():
                            continue

                        label_loc = container.locator(
                            'label, span.fb-form-element-label__title--is-required, '
                            'span[aria-hidden="true"], .fb-form-element__label'
                        ).first
                        label = label_loc.inner_text().strip() if label_loc.count() > 0 else "Campo"
                        label_corto = label[:55]

                        # --- Selects ---
                        select_box = container.locator('select')
                        if select_box.count() > 0:
                            v = select_box.input_value()
                            # Obtener las opciones disponibles
                            opciones_raw = select_box.locator('option').all()
                            opciones_texto = [o.inner_text().strip() for o in opciones_raw if o.inner_text().strip()]
                            PLACEHOLDERS = ("", "selecciona una opción", "select an option", "seleccione", "-- selecciona --")
                            opciones_reales = [o for o in opciones_texto if o.lower() not in PLACEHOLDERS]

                            if not v or v.lower() in PLACEHOLDERS:
                                if opciones_reales:
                                    console.print(f"  [magenta]🤖 Select IA:[/magenta] '{label_corto}' opciones: {opciones_reales}")
                                    try:
                                        elegida = elegir_opcion_select(label, opciones_reales, descripcion)
                                        select_box.select_option(label=elegida)
                                        v = select_box.input_value()
                                        console.print(f"  [cyan]📋 Select '[/cyan]{label_corto}[cyan]' → '{elegida}'[/cyan]")
                                        campos_rellenados.append({"label": label, "valor": elegida, "tipo": "select", "loc": select_box.first, "opciones": opciones_reales})
                                    except Exception as e:
                                        console.print(f"  [yellow]⚠️  Select IA falló: {e} — usando index 1[/yellow]")
                                        try:
                                            select_box.select_option(index=1)
                                            v = select_box.input_value()
                                            campos_rellenados.append({"label": label, "valor": v, "tipo": "select", "loc": select_box.first, "opciones": opciones_reales})
                                        except: pass
                                else:
                                    try:
                                        select_box.select_option(index=1)
                                        v = select_box.input_value()
                                        campos_rellenados.append({"label": label, "valor": v, "tipo": "select", "loc": select_box.first, "opciones": opciones_reales})
                                    except: pass
                            else:
                                console.print(f"  [dim]📋 '{label_corto}' ya tiene: '{v}'[/dim]")
                            continue

                        # --- Radios ---
                        radios = container.locator('input[type="radio"]')
                        if radios.count() > 0:
                            opciones_radio = []
                            all_radio_labels = container.locator('label').all()
                            for r_lbl in all_radio_labels:
                                l_txt = r_lbl.inner_text().strip()
                                if l_txt:
                                    opciones_radio.append({"texto": l_txt, "loc": r_lbl})
                            
                            valor_actual = ""
                            checked_loc = container.locator('input[type="radio"]:checked')
                            if checked_loc.count() > 0:
                                # Tratar de encontrar el label del radio checked
                                try:
                                    checked_id = checked_loc.get_attribute("id")
                                    if checked_id:
                                        lbl_match = container.locator(f'label[for="{checked_id}"]').first
                                        if lbl_match.count() > 0:
                                            valor_actual = lbl_match.inner_text().strip()
                                except: pass
                            
                            if not valor_actual:
                                try:
                                    # Por defecto marcamos el primero si no hay nada
                                    pl = container.locator('label').first
                                    pl.click()
                                    valor_actual = pl.inner_text().strip()
                                    console.print(f"  [cyan]🔘 Radio '[/cyan]{label_corto}[cyan]' → '{valor_actual}'[/cyan]")
                                except Exception as e:
                                    console.print(f"  [yellow]⚠️  Radio '{label_corto}': {e}[/yellow]")
                            else:
                                console.print(f"  [dim]🔘 '{label_corto}' ya marcado: '{valor_actual}'[/dim]")
                            
                            campos_rellenados.append({
                                "label": label, 
                                "valor": valor_actual, 
                                "tipo": "radio", 
                                "opciones": opciones_radio
                            })
                            continue

                        # --- Text / Number ---
                        text_input = container.locator('input[type="text"], input[type="number"], input[type="tel"], textarea')
                        if text_input.count() > 0:
                            v = text_input.first.input_value()
                            if not v:
                                t = tipo_campo(label)
                                if t == "telefono":
                                    valor = PERFIL_TELEFONO
                                    icono = "📞"
                                elif t == "email":
                                    valor = PERFIL_EMAIL
                                    icono = "📧"
                                elif t == "nombre":
                                    valor = PERFIL_NOMBRE
                                    icono = "👤"
                                elif t == "renta":
                                    valor = RENTA_ESPERADA
                                    icono = "💰"
                                elif t == "anos":
                                    icono = "🔢"
                                    console.print(f"  [magenta]🤖 IA:[/magenta] evaluando años para '{label_corto}'...")
                                    try:
                                        resp = responder_pregunta(label, descripcion)
                                        import re
                                        match = re.search(r'\d+', resp)
                                        valor = match.group() if match else "0"
                                    except Exception as e:
                                        valor = "0"
                                        console.print(f"  [red]   Error IA: {e}[/red]")
                                else:  # texto libre → IA
                                    icono = "🤖"
                                    console.print(f"  [magenta]🤖 IA:[/magenta] generando '{label_corto}'...")
                                    try:
                                        valor = responder_pregunta(label, descripcion)
                                        # Fallback extra: Si la pregunta es sobre plata/dinero, forzar extracción de números por si la IA falló
                                        if any(word in label.lower() for word in ["dólar", "usd", "peso", "$", "aspiración", "pretensiones", "sueldo", "salario", "renta"]):
                                            import re
                                            numeros = re.findall(r'\d+', valor)
                                            if numeros:
                                                valor = "".join(numeros) # ej: "1.000" -> "1000"
                                    except Exception as e:
                                        valor = "No especificado"
                                        console.print(f"  [red]   Error IA: {e}[/red]")

                                console.print(f"  [green]{icono} '{label_corto}'[/green] → [white]{valor[:80]}[/white]")
                                try:
                                    text_input.first.scroll_into_view_if_needed()
                                    text_input.first.click()
                                    _pausa(0.2, 0.7)
                                    text_input.first.fill("")
                                    # Simulate human typing
                                    text_input.first.press_sequentially(valor, delay=random.randint(100, 250))
                                except: pass
                                campos_rellenados.append({"label": label, "valor": valor, "tipo": t, "loc": text_input.first})
                            else:
                                console.print(f"  [dim]✏️  '{label_corto}' ya tiene: '{v[:40]}'[/dim]")
                            continue

                except Exception as e:
                    console.print(f"  [dim]Error escaneando: {e}[/dim]")

                # ── PAUSA INTERACTIVA: editar campos antes de continuar ──
                if campos_rellenados:
                    console.print("")
                    console.print("[bold white]  ¿Quieres editar algún campo antes de continuar?[/bold white]")
                    for i, c in enumerate(campos_rellenados):
                        console.print(f"    [dim][{i+1}][/dim] {c['label'][:50]} → [yellow]{c['valor'][:60]}[/yellow]")
                    console.print(f"    [dim][0][/dim] No editar — continuar")
                    console.print("")
                    while True:
                        try:
                            idx_str = input("  Número a editar [0 = continuar]: ").strip().lower()
                            if not idx_str or idx_str in ("0", "no", "n"):
                                break
                            idx = int(idx_str) - 1
                            if 0 <= idx < len(campos_rellenados):
                                campo = campos_rellenados[idx]
                                
                                # Caso Radio
                                if campo["tipo"] == "radio" and "opciones" in campo:
                                    opciones = campo["opciones"]
                                    console.print(f"  Opciones para '{campo['label'][:40]}':")
                                    for j, op in enumerate(opciones):
                                        console.print(f"    [{j+1}] {op['texto']}")
                                    
                                    sel_idx_str = input(f"  Elige el número [1-{len(opciones)}]: ").strip()
                                    try:
                                        sel_idx = int(sel_idx_str) - 1
                                        if 0 <= sel_idx < len(opciones):
                                            nuevo_valor = opciones[sel_idx]["texto"]
                                            opciones[sel_idx]["loc"].click()
                                            campos_rellenados[idx]["valor"] = nuevo_valor
                                            console.print(f"  [green]✅ Actualizado a: {nuevo_valor}[/green]")
                                        else:
                                            console.print("  [red]Opción inválida.[/red]")
                                    except ValueError:
                                        console.print("  [red]Entrada inválida.[/red]")

                                # Caso Select
                                elif campo["tipo"] == "select" and "opciones" in campo and campo.get("loc") is not None:
                                    loc = campo["loc"]
                                    opciones = campo["opciones"]
                                    console.print(f"  Opciones para '{campo['label'][:40]}':")
                                    for j, op in enumerate(opciones):
                                        console.print(f"    [{j+1}] {op}")
                                    
                                    sel_idx_str = input(f"  Elige el número [1-{len(opciones)}]: ").strip()
                                    try:
                                        sel_idx = int(sel_idx_str) - 1
                                        if 0 <= sel_idx < len(opciones):
                                            nuevo_valor = opciones[sel_idx]
                                            loc.select_option(label=nuevo_valor)
                                            campos_rellenados[idx]["valor"] = nuevo_valor
                                            console.print(f"  [green]✅ Actualizado a: {nuevo_valor}[/green]")
                                    except: pass

                                # Caso Texto/Número/Tel
                                elif campo.get("loc") is not None:
                                    try:
                                        loc = campo["loc"]
                                        nuevo = input(f"  Nuevo valor para '{campo['label'][:40]}': ").strip()
                                        if nuevo:
                                            loc.fill(nuevo)
                                            campos_rellenados[idx]["valor"] = nuevo
                                            console.print(f"  [green]✅ Actualizado[/green]")
                                    except Exception as e:
                                        console.print(f"  [red]Error al editar: {e}[/red]")
                        except (ValueError, KeyboardInterrupt):
                            break
                    console.print("")

                _pausa(0.5, 1)

                # 1. Retry si hay errores de validación
                error_msg = self.page.locator('.artdeco-inline-feedback--error, .fb-form-element__error-response').first
                if error_msg.count() > 0:
                    console.print(f"[yellow]⚠️  Validación fallida: '{error_msg.inner_text().strip()[:80]}'[/yellow]")
                    inputs = self.page.locator('input[type="text"]:visible, input[type="number"]:visible, input[type="tel"]:visible, input[type="radio"]:visible, select:visible').all()
                    for inp in inputs:
                        try:
                            t = inp.get_attribute("type") or ""
                            if t == "radio":   inp.check()
                            elif t == "tel":   inp.fill(PERFIL_TELEFONO)
                            elif t in ("text","number",""): inp.fill("2")
                            elif inp.tag_name == "select":  inp.select_option(index=1)
                        except: pass
                    _pausa(1, 2)

                # 2. Detectar botones de acción
                # LinkedIn moderno: el texto está en <span> dentro del <button>
                # aria-label es más fiable que :has-text()
                _pausa(0.5, 1)

                def _encontrar_boton(palabras: list) -> object:
                    """Busca un botón visible por aria-label o texto, retorna el locator o None."""
                    for p in palabras:
                        loc = self.page.locator(
                            f'button[aria-label*="{p}"], '
                            f'button:has-text("{p}")'
                        )
                        visibles = [b for b in loc.all() if b.is_visible()]
                        if visibles:
                            return visibles[0]
                    return None

                btn_submit = _encontrar_boton(["Enviar solicitud", "Submit application", "Postular"])
                btn_review = _encontrar_boton(["Revisar", "Review"])
                btn_next   = _encontrar_boton(["Siguiente", "Next", "Continuar", "Continue"])

                console.print(
                    f"  [dim]Botones detectados — "
                    f"Submit: {'✅' if btn_submit else '❌'}  "
                    f"Review: {'✅' if btn_review else '❌'}  "
                    f"Next: {'✅' if btn_next else '❌'}[/dim]"
                )

                if btn_submit:
                    # ── MODO REVISIÓN: mostrar resumen y pedir confirmación ──
                    if modo_revision:
                        console.print("")
                        resumen = detalle.get("resumen_ia", descripcion[:500] if descripcion else "(sin descripción)")

                        # console.print(Panel(
                        #     f"[bold yellow]🏢 Empresa:[/bold yellow] {detalle.get('empresa', 'Desconocida')}\n"
                        #     f"[bold yellow]💼 Cargo:[/bold yellow]   {detalle.get('titulo', oferta.get('titulo', ''))}\n"
                        #     f"[bold yellow]🔗 URL:[/bold yellow]     {oferta.get('url', '')}\n\n"
                        #     f"[italic dim]{resumen}[/italic dim]",
                        #     title="[bold cyan]📋 Revisión Final LinkedIn[/bold cyan]",
                        #     border_style="cyan", padding=(0, 1)
                        # ))
                        console.print("")
                        while True:
                            confirmacion = input("  🚀 ¿Confirmar postulación? [s = Sí / n = No]: ").strip().lower()
                            if confirmacion in ['s', 'n']:
                                break
                            console.print(f"  [red]⚠️ Te equivocaste, ingresa 's' o 'n' (escribiste: '{confirmacion}').[/red]")

                        if confirmacion != "s":
                            console.print("[dim]Postulación cancelada. Descartando formulario...[/dim]")
                            try:
                                self.page.locator('button[aria-label*="Cerrar"], button[aria-label*="Dismiss"], .artdeco-modal__dismiss').first.click()
                                _pausa(1, 2)
                                btn_discard = self.page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Descartar"), button:has-text("Discard")').first
                                if btn_discard.count() > 0:
                                    btn_discard.click()
                            except: pass
                            return "revision"

                    # ── ENVÍO REAL ──
                    console.print("[cyan]✉️  Enviando postulación...[/cyan]")
                    btn_submit.click()
                    _pausa(3, 5)
                    if self.page.locator('li:has-text("Postulación enviada"), .artdeco-modal__header:has-text("Postulación enviada"), .artdeco-inline-feedback--success').count() > 0:
                        console.print("[green]✅ ¡Postulación enviada con éxito![/green]")
                    registrar_postulacion(oferta_id, oferta.get("titulo", ""), oferta.get("empresa", ""), oferta.get("url", ""), "enviada", "")
                    return "enviada"

                if btn_review:
                    console.print("[cyan]↩️  Clic en Revisar...[/cyan]")
                    btn_review.click()
                    _pausa(1.5, 3)
                    continue

                if btn_next:
                    console.print(f"[cyan]➡️  Clic en Siguiente (paso {paso+1})...[/cyan]")
                    try:
                        btn_next.click()
                    except Exception:
                        btn_next.click(force=True)
                    _pausa(1.5, 3)
                    continue

                # Sin botones visibles → scroll y reintento
                console.print("[dim]⏳ Sin botones visibles, haciendo scroll...[/dim]")
                self.page.mouse.wheel(0, 300)
                _pausa(1, 2)
                if paso > 6:
                    console.print("[red]🛑 Demasiados pasos sin avanzar. Abortando.[/red]")
                    break
            
            return "error"

        except Exception as e:
            console.print(f"[red]❌ Error durante la postulación: {e}[/red]")
            return "error"

