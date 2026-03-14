import json
import os
import random
import time
from pathlib import Path
from playwright.sync_api import Page, BrowserContext
from rich.console import Console
from rich.panel import Panel

from config import CHILETRABAJOS_EMAIL, CHILETRABAJOS_PASSWORD, SESSION_PATH, cargar_perfil, CV_PATH
from database import ya_postule, registrar_postulacion
from ai_responder import responder_pregunta, resumir_oferta
from portales.base import PortalBase

console = Console()

# CV_PATH is now imported from config

def _pausa(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))

def scroll_aleatorio(page: Page):
    try:
        movimiento = random.randint(100, 500)
        page.mouse.wheel(0, movimiento)
        _pausa(0.5, 1.5)
    except Exception:
        pass


class ChileTrabajosPortal(PortalBase):
    
    def __init__(self, page: Page, context: BrowserContext):
        super().__init__(page, context)
        self.nombre = "ChileTrabajos"
        self.base_url = "https://www.chiletrabajos.cl"
        self.login_url = f"{self.base_url}/chtlogin"
        self.ofertas_url = f"{self.base_url}/buscar-empleos"

    def login(self) -> bool:
        """Inicia sesión en ChileTrabajos."""
        console.print(f"[cyan]Navegando a {self.login_url}[/cyan]")
        self.page.goto(self.login_url, timeout=60000)
        _pausa(1, 2)

        if "/panel" in self.page.url or "Mi cuenta" in self.page.content():
            print("✅ Sesión activa detectada (ChileTrabajos)")
            return True

        try:
            # Selectores exactos del HTML de ChileTrabajos:
            # <input name="username" id="username" type="text" ...>
            # <input name="password" id="password" type="password" ...>
            email_sel = 'input[name="username"], #username'
            pass_sel  = 'input[name="password"], #password'

            self.page.wait_for_selector(email_sel, timeout=15000)
            
            self.page.fill(email_sel, "")
            self.page.type(email_sel, CHILETRABAJOS_EMAIL.strip(), delay=random.randint(50, 150))
            _pausa(1.0, 2.0)
            
            self.page.fill(pass_sel, "")
            self.page.type(pass_sel, CHILETRABAJOS_PASSWORD.strip(), delay=random.randint(50, 150))
            _pausa(1.0, 2.0)
            
            # Botón: <input type="submit" value="Iniciar Sesión" name="login">
            btn_login = self.page.locator('input[type="submit"][name="login"], input[type="submit"][value="Iniciar Sesión"]').first
            
            try:
                box = btn_login.bounding_box()
                if box:
                    self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    _pausa(0.3, 0.8)
            except Exception:
                pass

            btn_login.click()

            # Esperar a ver si cambia de página o aparece algún elemento de login exitoso
            try:
                self.page.wait_for_selector('.alert-danger, .error', timeout=5000)
                # Si encuentra un error de credenciales
                print("❌ Login fallido — Credenciales inválidas.")
                return False
            except:
                pass # No hubo error visible rápido

            _pausa(2, 4)

            # Comprobar estado final
            if "chtlogin" not in self.page.url or "Cerrar sesión" in self.page.content() or "/panel" in self.page.url:
                print("✅ Login exitoso en ChileTrabajos")
                self._guardar_sesion()
                return True
            else:
                print(f"❌ Login fallido — la URL no cambió: {self.page.url}")
                return False
        except Exception as e:
            print(f"❌ Error en login ChileTrabajos: {e}")
            return False

    def _guardar_sesion(self):
        cookies = self.context.cookies()
        with open(SESSION_PATH, "w") as f:
            json.dump({"cookies": cookies}, f)
            
    def aplicar_filtros_avanzados(self, carrera: str, region: str):
        """Aplica filtros usando el formulario de búsqueda de la web."""
        from constantes import CT_CIUDADES
        import unicodedata
        
        self.carrera_actual = carrera
        self.region_actual = region
        
        self.ofertas_url = f"{self.base_url}/encuentra-un-empleo"
        console.print(f"  [cyan]🔍 Navegando al buscador interactivo: {self.ofertas_url}[/cyan]")
        self.page.goto(self.ofertas_url, timeout=60000)
        _pausa(1.5, 3.0)
        
        try:
            # 1. Llenar el campo 'Trabajo'
            input_trabajo = self.page.locator('#trabajo, input[name="2"]').first
            if input_trabajo.count() > 0:
                input_trabajo.fill("")
                input_trabajo.type(carrera, delay=random.randint(20, 50))
                _pausa(0.5, 1.0)
            
            # 2. Seleccionar la 'Ubicación'
            # En ChileTrabajos, CT_CIUDADES guarda los IDs (value) de la comuna/ciudad
            city_id = CT_CIUDADES.get(region, "")
            
            select_ubicacion = self.page.locator('select[name="13"]').first
            if select_ubicacion.count() > 0 and city_id:
                # Buscar por el "value" del combox
                try:
                    select_ubicacion.select_option(value=city_id)
                    _pausa(0.5, 1.0)
                except:
                    pass
            elif select_ubicacion.count() > 0 and region and region.lower() not in ("cualquiera", ""):
                 # Si no tenemos ID, usar el texto, por si acaso
                try:
                    select_ubicacion.select_option(label=region)
                    _pausa(0.5, 1.0)
                except:
                    pass
                        
            # 3. Hacer click en 'Buscar'
            # Chiletrabajos btn form
            btn_buscar = self.page.locator('form[action*="buscar-empleos"] button[type="submit"], #buscadorForm button[type="submit"]').first
            if btn_buscar.count() > 0:
                btn_buscar.click()
                try:
                    self.page.wait_for_load_state("load", timeout=15000)
                except:
                    pass
                _pausa(2, 3)
                
        except Exception as e:
            console.print(f"  [yellow]⚠️ Error aplicando filtros en el formulario: {e}[/yellow]")


    def obtener_ofertas(self, paginas: int = 3, num_pagina_actual: int = 1) -> list[dict]:
        """Obtiene las ofertas de la página actual de ChileTrabajos."""
        ofertas = []

        if num_pagina_actual > 1:
            console.print("  [dim]Buscando botón Siguiente en el paginador...[/dim]")
            btn_siguiente = self.page.query_selector('.pagination a[rel="next"], a:has-text("Siguiente"), a:has-text(">")')
            if btn_siguiente:
                btn_siguiente.scroll_into_view_if_needed()
                btn_siguiente.click()
                console.print(f"  [dim]Navegando a página {num_pagina_actual} (Clic Siguiente)[/dim]")
                _pausa(3, 5) 
            else:
                console.print("  [yellow]⚠️ No se encontró botón para avanzar a la página siguiente. Fin de resultados.[/yellow]")
                return []
        else:
            console.print(f"[dim]📄 Escaneando página 1 de resultados...[/dim]")

        # Esperar a que carguen las tarjetas. Según la imagen, las ofertas tienen un contenedor con un enlace
        try:
            self.page.wait_for_selector(".job-item, .oferta, div.row.mb-3, article", timeout=10000)
        except Exception:
            console.print(f"  [yellow]⚠️  No se encontraron más ofertas en esta página[/yellow]")
            return []

        # Extraer tarjetas (buscamos enlaces que parezcan de trabajos)
        tarjetas = self.page.query_selector_all("a[href*='/trabajo/']")

        for tarjeta in tarjetas:
            try:
                if random.random() < 0.3: scroll_aleatorio(self.page)
                    
                href = tarjeta.get_attribute("href") or ""
                if not href or "/trabajo/" not in href:
                    continue

                # Extraer ID: en ChileTrabajos la url es ej: /trabajo/analista-de-facturacion-3793214
                oferta_id = href.split("-")[-1]
                if not oferta_id.isdigit(): continue # Asegurar que es un id
                
                titulo = tarjeta.inner_text().strip()
                if not titulo: titulo = tarjeta.get_attribute("title") or "Sin Título"
                
                # Ignorar si es un link interno raro
                if len(titulo) < 3: continue
                    
                url_oferta = f"{self.base_url}{href}" if href.startswith("/") else href

                if any(o.get("id") == oferta_id for o in ofertas):
                    continue

                ofertas.append({
                    "id": oferta_id,
                    "titulo": titulo,
                    "url": url_oferta,
                })
            except Exception:
                continue

        _pausa(2, 5)
        return ofertas

    def obtener_detalle_oferta(self, url: str) -> dict:
        """Navega a la página de detalle y extrae información básica de la oferta."""
        # La URL de detalle es: /trabajo/slug-ID
        # La URL de postulación es: /trabajo/postular/ID
        self.page.goto(url, timeout=60000)
        _pausa(1.5, 2.5)

        detalle = {
            "titulo": "Sin título", "descripcion": "",
            "empresa": "Empresa no especificada", "preguntas": [],
            "ubicacion": "No especificada", "remoto": False,
        }

        try:
            titulo_h1 = self.page.query_selector("h1.title, h1")
            if titulo_h1: detalle["titulo"] = titulo_h1.inner_text().strip()

            try:
                page_text = self.page.evaluate("""
                    () => {
                        const bad = document.querySelectorAll('script,style,nav,footer,header,.publicidad');
                        bad.forEach(el => el.remove());
                        const box = document.querySelector('.box.border, .desc-oferta, #detalle-oferta, article');
                        return box ? box.innerText : document.body.innerText;
                    }
                """).strip()
                if page_text: detalle["descripcion"] = page_text[:8000]
            except Exception:
                body_el = self.page.query_selector("body")
                if body_el: detalle["descripcion"] = body_el.inner_text()[:8000]

            # Extraer tabla de atributos (ID, Buscado, Fecha, Ubicación, etc.)
            detalles_raw = self.page.evaluate("""
                () => {
                    const data = {};
                    const container = document.querySelector('.box.border');
                    if (!container) return data;
                    
                    const rows = container.querySelectorAll('.row, tr');
                    rows.forEach(row => {
                        const text = row.innerText.trim();
                        if (text.includes(':')) {
                            const parts = text.split(':');
                            if (parts.length >= 2) {
                                const key = parts[0].trim().toLowerCase();
                                const val = parts.slice(1).join(':').trim();
                                data[key] = val;
                            }
                        } else {
                            const label = row.querySelector('.col-sm-4, th, td:first-child');
                            const value = row.querySelector('.col-sm-8, td:last-child');
                            if (label && value && label.innerText.trim()) {
                                data[label.innerText.trim().toLowerCase()] = value.innerText.trim();
                            }
                        }
                    });
                    return data;
                }
            """)

            if detalles_raw:
                # Ubicación
                val_ubi = detalles_raw.get('ubicación') or detalles_raw.get('ubicacion')
                if val_ubi: detalle["ubicacion"] = str(val_ubi)
                
                # Empresa
                val_emp = detalles_raw.get('buscado') or detalles_raw.get('empresa')
                if val_emp: detalle["empresa"] = str(val_emp)
                
                # Remoto
                tipo = str(detalles_raw.get('tipo', '')).lower()
                u_text = str(detalle.get("ubicacion", "")).lower()
                desc_text = str(detalle.get("descripcion", "")).lower()
                
                detalle["remoto"] = (
                    "remoto" in tipo or "teletrabajo" in tipo or
                    "remoto" in u_text or "teletrabajo" in u_text or
                    "remoto" in desc_text or "teletrabajo" in desc_text or "home office" in desc_text
                )

                # Renta
                val_renta = detalles_raw.get('sueldo') or detalles_raw.get('renta')
                if val_renta:
                    # Limpiar caracteres no numéricos para el filtro
                    solo_num = "".join(filter(str.isdigit, str(val_renta)))
                    detalle["renta"] = solo_num
            else:
                emp_el = self.page.query_selector("h3.meta, .company-name, td")
                if emp_el: detalle["empresa"] = emp_el.inner_text().strip().split("\n")[0]

        except Exception as e:
            print(f"  ⚠️ Error extrayendo detalle: {e}")

        return detalle


    def postular_oferta(self, oferta: dict, detalle: dict, modo_revision: bool = True) -> str:
        oferta_id = oferta["id"]
        titulo = oferta.get("titulo", "")
        empresa = oferta.get("empresa", "")
        url = oferta.get("url", "")
        descripcion = detalle.get("descripcion", "")

        if ya_postule(oferta_id):
            return "duplicado"

        # console.print(Panel.fit(
        #     f"[bold yellow]💼 {titulo}[/bold yellow]\n[cyan]🏢 {empresa}[/cyan]\n[dim]🔗 {url}[/dim]",
        #     title="[bold white]OFERTA (ChileTrabajos)[/bold white]", border_style="bright_blue"
        # ))

        # ChileTrabajos: la página de postulación es /trabajo/postular/{id}
        # Construimos la URL directa del formulario
        url_postular = f"{self.base_url}/trabajo/postular/{oferta_id}"
        console.print(f"  [dim]Abriendo formulario: {url_postular}[/dim]")
        self.page.goto(url_postular, timeout=60000)
        self.page.wait_for_load_state("load", timeout=15000)
        _pausa(1, 2)

        # Detectar si ya postulamos
        contenido = self.page.content()
        if "Ya has postulado" in contenido or "ya postulaste" in contenido.lower():
            console.print("  [dim]Ya postulado anteriormente.[/dim]")
            registrar_postulacion(oferta_id, titulo, empresa, url, "duplicado", "")
            return "duplicado"

        # ── 1. Detectar y generar respuestas para preguntas dinámicas q2/q3/q4 ──
        # Busca todos los textarea identificados por id qN y su etiqueta
        preguntas_detectadas = self.page.query_selector_all(
            "textarea.questionText, textarea[name^='q'], textarea[id^='q']"
        )
        respuestas_generadas = []

        for ta in preguntas_detectadas:
            try:
                campo_name = ta.get_attribute("name") or ta.get_attribute("id") or ""
                # El label está en el label del form-group padre
                label_hidden = self.page.query_selector(f'input[name="{campo_name}_label"]')
                if label_hidden:
                    label_text = label_hidden.get_attribute("value") or campo_name
                else:
                    # buscar label hermano
                    label_el = self.page.query_selector(f'label[for="{ta.get_attribute("id") or ""}"]')
                    label_text = label_el.inner_text().strip() if label_el else campo_name

                # console.print(f"  [dim]🤖 Generando respuesta para: {label_text[:70]}[/dim]")
                respuesta = responder_pregunta(label_text, descripcion)
                # Limitar a 255 chars (máximo del campo)
                respuesta = respuesta[:250] if len(respuesta) > 250 else respuesta
                respuestas_generadas.append({
                    "pregunta": label_text,
                    "respuesta": respuesta,
                    "name": campo_name,
                })
            except Exception as ex:
                console.print(f"  [yellow]⚠️ Error detectando pregunta: {ex}[/yellow]")

        if respuestas_generadas:
            console.print(f"[dim]  → Generando {len(respuestas_generadas)} respuesta(s)...[/dim]")
            for r in respuestas_generadas:
                _pausa(0.5, 1.0)

        # ── 2. Modo revisión interactivo ──
        perfil = cargar_perfil()
        renta_esperada = str(perfil.get("preferencias", {}).get("renta_esperada", "800000")).replace(".", "").replace(",", "")
        disponibilidad = perfil.get("preferencias", {}).get("disponibilidad", "Inmediata")

        if modo_revision:
            # Mostrar preguntas y respuestas de forma clara
            if respuestas_generadas:
                console.print(f"\n[bold white]{'─'*80}[/bold white]")
                console.print(f"[bold white]  📝 RESPUESTAS GENERADAS ({len(respuestas_generadas)} pregunta/s)[/bold white]")
                console.print(f"[bold white]{'─'*80}[/bold white]")
                for i, r in enumerate(respuestas_generadas, 1):
                    # Usamos .get() por seguridad con los tipos
                    pregunta_txt = str(r.get("pregunta", ""))[:100]
                    respuesta_txt = str(r.get("respuesta", ""))
                    console.print(f"\n  [bold yellow]❓ P{i}:[/bold yellow] [yellow]{pregunta_txt}[/yellow]")
                    console.print(Panel(
                        f"[white]{respuesta_txt}[/white]",
                        border_style="green", padding=(0, 1)
                    ))
            console.print("")

            # Edición opcional de respuestas
            while respuestas_generadas:
                console.print(f"  [dim]Opciones:[/dim]")
                console.print(f"  [dim]- [bold]1[/bold] hasta [bold]{len(respuestas_generadas)}[/bold] para editar la respectiva respuesta[/dim]")
                console.print(f"  [dim]- [bold]ENTER[/bold] para continuar[/dim]")
                
                opcion = input(f"  ✏️  ¿Deseas editar alguna respuesta?: ").strip().lower()
                
                if not opcion:
                    break
                    
                if not opcion.isdigit() or not (1 <= int(opcion) <= len(respuestas_generadas)):
                    console.print(f"  [red]⚠️ Te equivocaste. Ingresa un número entre 1 y {len(respuestas_generadas)} o presiona ENTER.[/red]\n")
                    continue
                    
                idx = int(opcion) - 1
                r_edit = respuestas_generadas[idx]
                console.print(f"  [dim]Pregunta seleccionada:[/dim] [yellow]{str(r_edit.get('pregunta', ''))[:100]}[/yellow]")
                nueva = input(f"  Nueva respuesta: ").strip()
                if nueva:
                    r_edit['respuesta'] = nueva[:250]
                    console.print(f"  [green]✅ Respuesta P{idx+1} actualizada[/green]\n")
                else:
                    console.print(f"  [yellow]⚠️ Edición cancelada. Respuesta sin cambios.[/yellow]\n")

            console.print("")
            while True:
                try:
                    renta_fmt = f"${int(renta_esperada):,}".replace(",", ".")
                    renta_input = input(f"  💰 Renta pretendida [Enter = {renta_fmt}]: ").strip()
                except:
                    renta_input = input(f"  💰 Renta pretendida: ").strip()

                if not renta_input:
                    break
                limpia = "".join(filter(str.isdigit, renta_input))
                if limpia:
                    renta_esperada = limpia
                    break
                else:
                    console.print("  [red]⚠️ Te equivocaste, ingresa solo números o presiona ENTER para el valor por defecto.[/red]")

            try:
                console.print(f"  [dim]Renta a enviar: [bold]${int(renta_esperada):,}[/bold][/dim]".replace(",", "."))
            except: pass

            dispo_input = input(f"  📅 Disponibilidad [Enter = {disponibilidad}]: ").strip()
            if dispo_input:
                disponibilidad = dispo_input

            console.print("")
            while True:
                confirmacion = input("  🚀 ¿Confirmar postulación con estas respuestas? [s = Sí / n = No]: ").strip().lower()
                if confirmacion in ['s', 'n']:
                    break
                console.print(f"  [red]⚠️ Te equivocaste, ingresa 's' o 'n' (escribiste: '{confirmacion}').[/red]")

            if confirmacion != "s":
                registrar_postulacion(oferta_id, titulo, empresa, url, "saltada",
                                      json.dumps(respuestas_generadas, ensure_ascii=False))
                return "saltada"

        # ── 3. Rellenar el formulario ──
        try:
            # 3a. Carta de presentación (puede ya tener texto por defecto)
            carta_el = self.page.query_selector("#carta, textarea[name='app_letter']")
            if carta_el:
                carta_existente = carta_el.input_value() or ""
                if not carta_existente.strip():
                    # Generar carta si está vacía
                    carta = responder_pregunta("Carta de presentación", descripcion)
                    carta_el.click()
                    carta_el.fill(carta[:2000])
                    _pausa(0.5, 1.0)
                else:
                    console.print("  [dim]✅ Carta de presentación ya pre-completada por el perfil.[/dim]")

            # 3b. Renta
            salary_el = self.page.query_selector("input[name='salary'], #salary")
            if salary_el:
                salary_el.click()
                salary_el.fill(str(renta_esperada))
                _pausa(0.3, 0.6)

            # 3c. Disponibilidad
            dispo_el = self.page.query_selector("input[name='disp'], #dispo")
            if dispo_el:
                # Si es inmediata, hacer clic en el checkbox
                if disponibilidad.lower() in ("inmediata", "disponibilidad inmediata"):
                    chk = self.page.query_selector("#dispoIn")
                    if chk:
                        chk.check()
                    else:
                        dispo_el.fill("Inmediata")
                else:
                    dispo_el.fill(disponibilidad)
                _pausa(0.3, 0.6)

            # 3d. Preguntas dinámicas q2, q3, q4...
            for r in respuestas_generadas:
                campo = r["name"]
                ta_el = self.page.query_selector(
                    f"textarea[name='{campo}'], #{campo}"
                )
                if ta_el:
                    ta_el.scroll_into_view_if_needed()
                    ta_el.click()
                    ta_el.fill("")
                    # Escribir char a char para simular humano
                    for ch in r["respuesta"]:
                        ta_el.type(ch, delay=random.randint(15, 50))
                    _pausa(0.3, 0.8)

            # 3e. Subir CV — OBLIGATORIO
            if not os.path.exists(CV_PATH):
                console.print(f"  [bold red]❌ ERROR: No se encontró el CV en '{CV_PATH}'[/bold red]")
                console.print("  [yellow]Asegúrate de que el archivo 'cv_joseluis.pdf' exista en la carpeta portales/[/yellow]")
                estado = "error_cv"
                registrar_postulacion(oferta_id, titulo, empresa, url, estado, "")
                return estado

            cv_input = self.page.query_selector("input[name='att1'], #cv")
            if not cv_input:
                console.print("  [bold red]❌ ERROR: No se encontró el campo para subir CV en el formulario[/bold red]")
                estado = "error_cv"
                registrar_postulacion(oferta_id, titulo, empresa, url, estado, "")
                return estado

            console.print(f"  [cyan]📎 Subiendo CV desde: {CV_PATH}...[/cyan]")
            cv_input.set_input_files(CV_PATH)
            _pausa(0.8, 1.2)

            # Verificar que el nombre del archivo aparece en el label
            try:
                label_cv = self.page.query_selector("label[for='cv'], .custom-file-label")
                nombre_mostrado = label_cv.inner_text() if label_cv else ""
                if "cv_joseluis" in nombre_mostrado.lower() or ".pdf" in nombre_mostrado.lower():
                    console.print("  [bold green]✅ CV subido correctamente[/bold green]")
                else:
                    console.print(f"  [green]✅ CV adjuntado (label: {nombre_mostrado or 'OK'})[/green]")
            except Exception:
                console.print("  [green]✅ CV adjuntado[/green]")


            _pausa(1, 2)

            # 3f. Enviar postulación
            # El botón de envío es: <input type="submit" name="apply" value="Enviar postulación">
            btn_enviar = self.page.query_selector(
                'input[name="apply"][type="submit"], input[type="submit"][class*="enviar-postulacion"]'
            )
            if not btn_enviar:
                btn_enviar = self.page.query_selector('input[type="submit"]')

            if btn_enviar:
                btn_enviar.scroll_into_view_if_needed()
                _pausa(0.5, 1.0)
                btn_enviar.click()
                _pausa(2, 4)

                # Verificar éxito
                contenido_post = self.page.content()
                if ("postulaci" in contenido_post.lower() and
                        ("gracias" in contenido_post.lower() or
                         "enviada" in contenido_post.lower() or
                         "exitosa" in contenido_post.lower() or
                         "tu postulación" in contenido_post.lower())):
                    console.print("  [bold green]✅ Postulación enviada correctamente[/bold green]")
                    estado = "enviada"
                else:
                    console.print("  [green]✅ Formulario enviado[/green]")
                    estado = "enviada"
            else:
                console.print("  [red]❌ No se encontró el botón de envío[/red]")
                estado = "error_boton"

        except Exception as e:
            console.print(f"  [red]❌ Error al rellenar/enviar: {e}[/red]")
            estado = "error"

        registrar_postulacion(oferta_id, titulo, empresa, url, estado,
                              json.dumps(respuestas_generadas, ensure_ascii=False))
        return estado
