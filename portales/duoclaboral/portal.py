import os
import json
import random
import time
from playwright.sync_api import Page, BrowserContext
from rich.console import Console
from rich.panel import Panel
from urllib.parse import quote

from config import DUOC_EMAIL, DUOC_PASSWORD, LOGIN_URL, OFERTAS_URL, SESSION_PATH, cargar_perfil, CV_PATH
from database import ya_postule, registrar_postulacion
from ai_responder import responder_pregunta, resumir_oferta
from portales.base import PortalBase

console = Console()

def _pausa(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))

def scroll_aleatorio(page: Page):
    try:
        movimiento = random.randint(100, 500)
        page.mouse.wheel(0, movimiento)
        _pausa(0.5, 1.5)
    except Exception:
        pass


class DuocLaboralPortal(PortalBase):
    
    def __init__(self, page: Page, context: BrowserContext):
        super().__init__(page, context)
        self.nombre = "DuocLaboral"

    def login(self) -> bool:
        """Inicia sesión en DuocLaboral."""
        self.page.goto(LOGIN_URL, timeout=60000)
        _pausa()

        if "login" not in self.page.url:
            print("✅ Sesión activa detectada")
            return True

        try:
            email_sel = '#username, input[name="LoginForm[username]"], input[type="email"]'
            pass_sel  = '#password, input[name="LoginForm[password]"], input[type="password"]'

            self.page.wait_for_selector(email_sel, timeout=10000)
            
            self.page.fill(email_sel, "")
            self.page.type(email_sel, DUOC_EMAIL.strip(), delay=random.randint(50, 150))
            _pausa(1.0, 2.0)
            
            self.page.fill(pass_sel, "")
            self.page.type(pass_sel, DUOC_PASSWORD.strip(), delay=random.randint(50, 150))
            _pausa(1.0, 2.0)
            
            try:
                box = self.page.locator('#userLoginSubmit, button[type="submit"], input[type="submit"]').bounding_box()
                if box:
                    self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    _pausa(0.3, 0.8)
            except Exception:
                pass

            self.page.click('#userLoginSubmit, button[type="submit"], input[type="submit"]')

            try:
                self.page.wait_for_function('window.location.pathname !== "/login"', timeout=15000)
            except Exception:
                pass 
            
            _pausa(1, 2)

            if "login" not in self.page.url:
                print("✅ Login exitoso")
                self._guardar_sesion()
                return True
            else:
                print(f"❌ Login fallido — la URL no cambió: {self.page.url}")
                return False
        except Exception as e:
            print(f"❌ Error en login: {e}")
            return False

    def _guardar_sesion(self):
        cookies = self.context.cookies()
        with open(SESSION_PATH, "w") as f:
            json.dump({"cookies": cookies}, f)

    def aplicar_filtros_avanzados(self, carrera: str, region: str):
        """Navega a la búsqueda usando filtros de carrera y región (por IDs)."""
        from constantes import DUOC_CARRERAS, DUOC_REGIONES, DUOC_COMUNAS, DUOC_MODALIDADES
        from config import FILTROS
        
        carrera_id = DUOC_CARRERAS.get(carrera, "")
        
        # Determinar si la region es una Región o una Comuna
        region_id = DUOC_REGIONES.get(region, "")
        comuna_id = ""
        
        if not region_id:
            comuna_id = DUOC_COMUNAS.get(region, "")
            
        modalidad_nombre = FILTROS.get("modalidad", "")
        modalidad_id = DUOC_MODALIDADES.get(modalidad_nombre, "")

        # Construir URL de búsqueda
        # Filtros base: carrera, region (region), comuna (commune), modalidad (remote)
        query_params = []
        if carrera_id: query_params.append(f"Search[genericCareer]={carrera_id}")
        if region_id: query_params.append(f"Search[region]={region_id}")
        if comuna_id: query_params.append(f"Search[commune]={comuna_id}")
        if modalidad_id: query_params.append(f"Search[remote]={modalidad_id}")
        
        filter_url = f"{OFERTAS_URL}?" + "&".join(query_params)
        
        console.print(f"🔍 [cyan]Navegando a búsqueda filtrada:[/cyan] [dim]{filter_url}[/dim]")
        self.page.goto(filter_url, timeout=60000)
        _pausa(3, 5)
        try:
            self.page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        _pausa(1, 2)


    def obtener_ofertas(self, paginas: int = 3, num_pagina_actual: int = 1) -> list[dict]:
        """Obtiene ofertas de la página actual de DuocLaboral usando selectores correctos del HTML real."""
        ofertas = []

        if num_pagina_actual > 1:
            # Paginación: buscar enlace "Siguiente" o úrrow en el paginador
            btn_siguiente = self.page.query_selector(
                '.pagination a[rel="next"], li.next a'
            )
            if not btn_siguiente:
                # Intentar hacer clic en el número de página siguiente
                try:
                    num_links = self.page.query_selector_all('.pagination a')
                    for lnk in num_links:
                        txt = lnk.inner_text().strip()
                        if txt == str(num_pagina_actual):
                            btn_siguiente = lnk
                            break
                except Exception:
                    pass

            if btn_siguiente:
                btn_siguiente.scroll_into_view_if_needed()
                btn_siguiente.click()
                console.print(f"  [dim]Navegando a página {num_pagina_actual}...[/dim]")
                _pausa(2, 3)
            else:
                console.print("  [yellow]⚠️ Fin de resultados (no hay página siguiente).[/yellow]")
                return []
        else:
            console.print(f"[dim]📄 Escaneando página 1...[/dim]")

        try:
            self.page.wait_for_selector("article.job-card, .job-card", timeout=10000)
        except Exception:
            console.print(f"  [yellow]⚠️  No se encontraron ofertas en esta página[/yellow]")
            return []

        # Las tarjetas en DuocLaboral son <article class="job-card"> con un enlace <a href="/jobs/ID">
        articulos = self.page.query_selector_all("article.job-card")
        console.print(f"  [dim]Encontré {len(articulos)} tarjetas en esta página.[/dim]")

        for art in articulos:
            try:
                if random.random() < 0.2: scroll_aleatorio(self.page)

                # Saltar las que ya marcaron "Ya postulaste" en la tarjeta
                ya_aplicado = art.query_selector(".job-card-applied")
                if ya_aplicado:
                    continue

                # Enlace principal del trabajo: <a href="/jobs/856396">
                enlace = art.query_selector("a[href*='/jobs/']") or art.query_selector("h2 a, .job-card-title a")
                if not enlace:
                    continue

                href = enlace.get_attribute("href") or ""
                if not href:
                    continue

                # ID es el último segmento de /jobs/856396
                oferta_id = href.rstrip("/").split("/")[-1]
                if not oferta_id.isdigit():
                    continue

                # Título desde el elemento span dentro del enlace
                titulo_el = enlace.query_selector("span[itemprop='title']")
                titulo = titulo_el.inner_text().strip() if titulo_el else enlace.inner_text().strip()
                if len(titulo) < 3:
                    titulo = "Oferta sin título"

                # Empresa
                emp_el = art.query_selector(".job-card-company span[itemprop='name']")
                empresa = emp_el.inner_text().strip() if emp_el else ""

                url_oferta = f"https://duoclaboral.cl{href}" if href.startswith("/") else href

                if any(o.get("id") == oferta_id for o in ofertas):
                    continue

                ofertas.append({
                    "id": oferta_id,
                    "titulo": titulo,
                    "empresa": empresa,
                    "url": url_oferta,
                })
            except Exception:
                continue

        _pausa(1, 2)
        return ofertas

    def obtener_detalle_oferta(self, url: str) -> dict:
        # Ya navegamos en main.py, pero por seguridad esperamos a que cargue algo del detalle
        try:
            self.page.wait_for_selector(".job-detail-card, .job-detail-content, h1", timeout=15000)
        except: pass

        _pausa(2, 4) 
        for _ in range(random.randint(1, 2)): scroll_aleatorio(self.page)

        detalle = {
            "titulo": "Sin título", "descripcion": "", "empresa": "Empresa no especificada",
            "preguntas": [], "renta_selector": None, "submit_selector": None,
        }

        try:
            # --- PRIORIDAD 1: JSON-LD (Estructurado y super confiable) ---
            try:
                json_ld_scripts = self.page.query_selector_all("script[type='application/ld+json']")
                for script in json_ld_scripts:
                    import json
                    try:
                        data = json.loads(script.inner_text())
                        if isinstance(data, dict) and data.get("@type") == "JobPosting":
                            desc = detalle.get("descripcion") or ""
                            if not desc or len(desc) < 100:
                                detalle["descripcion"] = data.get("description", "").replace("\r\n", "\n")
                            if data.get("title"): detalle["titulo"] = data.get("title")
                            if data.get("hiringOrganization", {}).get("name"): 
                                detalle["empresa"] = data.get("hiringOrganization").get("name")
                            # Salarios
                            base_salary = data.get("baseSalary", {})
                            if isinstance(base_salary, dict) and base_salary.get("value", {}).get("value"):
                                detalle["renta"] = str(base_salary["value"]["value"])
                    except: continue
            except: pass

            # --- PRIORIDAD 2: SELECTORES VISUALES ---
            if not detalle.get("titulo") or detalle["titulo"] == "Sin título":
                t_el = self.page.query_selector("h1, .job-detail-title")
                if t_el: detalle["titulo"] = t_el.inner_text().strip()

            desc_v = detalle.get("descripcion") or ""
            if not desc_v or len(desc_v) < 50:
                desc_selectors = [
                    ".job-detail-content",
                    "[itemprop='description']",
                    ".job_description",
                    ".descripcion",
                    "#description",
                    ".job-description-details"
                ]
                for sel in desc_selectors:
                    el = self.page.query_selector(sel)
                    if el:
                        txt = el.inner_text().strip()
                        if len(txt) > 20: 
                            detalle["descripcion"] = txt
                            break
            
            # Fallback agresivo
            if not detalle["descripcion"]:
                detalle["descripcion"] = self.page.evaluate("""() => {
                    const main = document.querySelector('main, article, #content, .job-detail-card');
                    if (main) {
                        const clone = main.cloneNode(true);
                        clone.querySelectorAll('script, style, nav, footer, header, button, .job-related-section').forEach(e => e.remove());
                        return clone.innerText.trim();
                    }
                    return document.body.innerText.trim().substring(0, 5000);
                }""")

            # Empresa (si no se sacó de JSON-LD)
            if detalle["empresa"] == "Empresa no especificada":
                emp_el = self.page.query_selector(".company-profile-name, .company-name, .logo-company + p, h2")
                if emp_el: detalle["empresa"] = emp_el.inner_text().strip()

            # Ubicación
            loc_el = self.page.query_selector(".job-detail-item-content span[itemprop='addressLocality'], .location, .ubicacion")
            if not loc_el:
                for txt in ["text=/Región/i", "text=/Ciudad/i", "[title*='Ubicación']", ".job-location"]:
                    loc_el = self.page.query_selector(txt)
                    if loc_el: break
            
            if loc_el: 
                detalle["ubicacion"] = loc_el.inner_text().strip()
            else: 
                detalle["ubicacion"] = "No especificada"

            # Detectar si es remoto (Teletrabajo)
            full_text = f"{detalle.get('titulo', '')} {detalle.get('descripcion', '')}".lower()
            u_lower = (detalle.get("ubicacion") or "No especificada").lower()
            detalle["remoto"] = any(x in full_text for x in ["remoto", "teletrabajo", "home office", "homeoffice", "desde casa"]) or "remoto" in u_lower

            # Intentar extraer renta de la descripción (ej: $800.000, Sueldo: 900000)
            import re
            m = re.search(r'(?:sueldo|renta|líquido|pago)\s*(?::|de)?\s*(?:\$)?\s*(\d{1,3}(?:\.?\d{3})*)', full_text)
            if m:
                renta_str = m.group(1).replace(".", "")
                detalle["renta"] = renta_str

            # Extraer nivel de experiencia requerido (si existe)
            try:
                exp_els = self.page.query_selector_all(".job-req-item")
                for el in exp_els:
                    lbl = el.query_selector(".job-req-label")
                    if lbl and "experiencia" in lbl.inner_text().strip().lower():
                        val = el.query_selector(".job-req-value")
                        if val:
                            detalle["experiencia"] = val.inner_text().strip()
                            break
            except Exception:
                pass

            # --- EXTRACCIÓN ESTRUCTURADA (Metadatos) ---
            metadata = {}
            try:
                # En DuocLaboral, los detalles están en .job-detail-item o .job-req-item
                items = self.page.query_selector_all(".job-detail-item, .job-req-item")
                for item in items:
                    label_el = item.query_selector(".job-detail-item-label, .job-req-label")
                    value_el = item.query_selector(".job-detail-item-value, .job-req-value")
                    if label_el and value_el:
                        lbl = label_el.inner_text().strip().rstrip(":")
                        val = value_el.inner_text().strip()
                        if lbl and val:
                            metadata[lbl] = val
                            # Si es sueldo, guardarlo también en detalle["renta"]
                            if "sueldo" in lbl.lower():
                                val_clean = val.replace("$", "").replace(".", "").strip()
                                if val_clean.isdigit(): detalle["renta"] = val_clean
            except Exception: pass
            detalle["metadata"] = metadata

            # Si no se encontró por .job-req-item, intentar por una tabla o lista de pares
            if not metadata:
                try:
                    # Alternativa: pares de texto en la descripción o en un div específico
                    detalles_texto = self.page.locator(".job-description-details, .job-details").inner_text()
                    lines = detalles_texto.split("\n")
                    for line in lines:
                        if ":" in line:
                            parts = line.split(":", 1)
                            metadata[parts[0].strip()] = parts[1].strip()
                except: pass

            form_container_selectors = [
                "form:has(button#sendApplication)", 
                "form.job-apply-form", 
                ".application-form", 
                "#postulacion", 
                ".postulacion-container",
                ".job-apply-container"
            ]
            form_container = None
            for sel in form_container_selectors:
                form_container = self.page.query_selector(sel)
                if form_container: break
            
            preguntas_encontradas = []
            
            # Buscamos elementos de entrada (textareas e inputs de texto)
            seleclor_inputs = "textarea, input[type='text'], input:not([type])"
            if form_container:
                all_inputs = form_container.query_selector_all(seleclor_inputs)
            else:
                all_inputs = self.page.query_selector_all(seleclor_inputs)
                
            idx_q = 0   # índice de preguntas (excluyendo renta)
            dom_idx = 0  # índice DOM real (todos los inputs visibles, incluyendo renta)
            for el_input in all_inputs:
                try:
                    if not el_input.is_visible():
                        continue
                    
                    # Guardar ORIGINAL para selectores CSS (case-sensitive)
                    nm_orig    = el_input.get_attribute("name") or ""
                    id_orig    = el_input.get_attribute("id") or ""
                    # Copia en minúscula SOLO para comparaciones de palabras clave
                    ph         = (el_input.get_attribute("placeholder") or "").lower()
                    nm         = nm_orig.lower()
                    id_attr    = id_orig.lower()
                    
                    # Ignorar campos técnicos o de búsqueda
                    if any(k in ph for k in ["buscar", "search", "filtro"]) or \
                       any(k in nm for k in ["chat", "search", "filter", "csrf", "token"]) or \
                       any(k in id_attr for k in ["chat", "search", "filter"]):
                        continue
                        
                    # Extraer Label con búsqueda multi-nivel
                    js_eval = """
                    el => {
                        let labelTxt = "";
                        // 1. Direct label[for=id]
                        if (el.id) {
                            let lbl = document.querySelector('label[for="' + el.id + '"]');
                            if (lbl) labelTxt = lbl.innerText.trim();
                        }
                        // 2. aria-labelledby
                        if (!labelTxt && el.getAttribute('aria-labelledby')) {
                            let lbl = document.getElementById(el.getAttribute('aria-labelledby'));
                            if (lbl) labelTxt = lbl.innerText.trim();
                        }
                        // 3. Parent labels (up to 3 levels)
                        if (!labelTxt) {
                            let curr = el;
                            for (let i = 0; i < 3; i++) {
                                if (!curr) break;
                                let lbl = curr.querySelector('label');
                                if (lbl) { labelTxt = lbl.innerText.trim(); break; }
                                curr = curr.parentElement;
                            }
                        }
                        // 4. Previous sibling label
                        if (!labelTxt) {
                            let prev = el.previousElementSibling;
                            if (prev && prev.tagName === 'LABEL') labelTxt = prev.innerText.trim();
                        }
                        // 5. Fallback attributes
                        if (!labelTxt) {
                            labelTxt = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || "";
                        }
                        return labelTxt.replace(/:$/, "").trim();
                    }
                    """
                    label = el_input.evaluate(js_eval) or f"Pregunta {idx_q + 1}"
                    
                    # DETERMINAR SI ES EL CAMPO DE RENTA
                    salary_kws = ["renta", "sueldo", "pretensión", "pretension", "expectativa", "salary", "monto", "monto requerido"]
                    numeric_kws = ["solo números", "solo numeros", "ingrese números", "ingrese numeros"]
                    
                    pattern_attr = el_input.get_attribute("pattern") or ""
                    inputmode_attr = el_input.get_attribute("inputmode") or ""
                    is_salary_pattern = ("[0-9" in pattern_attr) or (inputmode_attr == "decimal")
                    
                    is_first_input = (dom_idx == 0)
                    maybe_salary = is_salary_pattern or any(k in label.lower() or k in ph or k in nm or k in id_attr for k in salary_kws)
                    
                    if maybe_salary or (is_first_input and any(k in ph for k in numeric_kws)):
                        # Usar valores originales en selectores CSS
                        if nm_orig:
                            detalle["renta_selector"] = f"[name='{nm_orig}']"
                        elif id_orig:
                            detalle["renta_selector"] = f"#{id_orig}"
                        else:
                            detalle["renta_selector"] = None
                        detalle["renta_field_name"] = nm_orig  # valor original para comparación
                        detalle["renta_field_id"]   = id_orig
                        dom_idx += 1
                        if detalle["renta_selector"]: continue
                    
                    preguntas_encontradas.append({
                        "label":   label,
                        "indice":  idx_q,   # numeración al usuario
                        "dom_idx": dom_idx, # posición DOM real para fallback
                        "name":    nm_orig, # ORIGINAL para selector CSS
                        "id":      id_orig, # ORIGINAL para selector CSS
                        "tipo":    el_input.evaluate("el => el.tagName.toLowerCase()")
                    })
                    idx_q += 1
                    dom_idx += 1
                except: continue
            
            detalle["preguntas"] = preguntas_encontradas

            # Botón de envío
            btn_selector = 'button#sendApplication.job-apply-btn, button:has-text("Enviar postulación"), button:has-text("Enviar postulacion"), .btn-postular'
            btn = (form_container.query_selector(btn_selector)) if form_container else self.page.query_selector(btn_selector)
            if btn: detalle["submit_selector"] = btn_selector

        except Exception as e: print(f"  ⚠️  Error extrayendo detalle: {e}")
        return detalle

    def postular_oferta(self, oferta: dict, detalle: dict, modo_revision: bool = True) -> str:
        oferta_id = oferta["id"]
        titulo = oferta.get("titulo", "")
        empresa = oferta.get("empresa", "")
        url = oferta.get("url", "")

        if ya_postule(oferta_id): return "duplicado"

        # Eliminamos el goto y el Panel redundante porque main.py ya lo hace.
        # self.page.goto(url, timeout=60000)
        _pausa(1, 2)
        
        if self.page.locator("text='Ya postulaste'").count() > 0 or self.page.locator("text='Postulado'").count() > 0:
            return "duplicado"
            
        respuestas_generadas = []
        btn_enviar = self.page.locator("button#sendApplication.btn.btn-primary.job-apply-btn")
        if btn_enviar.count() == 0:
            btn_postular_alt = self.page.locator("button.button-apply, .btn-postular")
            if btn_postular_alt.count() == 0: return "error"

        descripcion = detalle.get("descripcion", "")
        preguntas = detalle.get("preguntas", [])

        # Re-detectar preguntas si no se encontraron en obtener_detalle_oferta (SOLO en el form)
        if not preguntas:
            try:
                form_container = self.page.query_selector('form:has(button#sendApplication), form.job-apply-form, .application-form, #apply, .job-apply-container')
                seleclor_inputs = "textarea, input[type='text'], input:not([type])"
                all_inputs = (form_container.query_selector_all(seleclor_inputs) if form_container else self.page.query_selector_all(seleclor_inputs))
                
                idx_q = 0   # contador de preguntas
                dom_idx = 0  # contador de posición DOM real
                for el_input in all_inputs:
                    try:
                        if not el_input.is_visible(): continue
                        # Guardar ORIGINAL para selectores CSS
                        nm_orig  = el_input.get_attribute("name") or ""
                        id_orig  = el_input.get_attribute("id") or ""
                        ph       = (el_input.get_attribute("placeholder") or "").lower()
                        nm       = nm_orig.lower()
                        id_attr  = id_orig.lower()
                        
                        if any(k in ph for k in ["buscar", "search"]) or any(k in nm for k in ["chat", "search", "csrf"]) or any(k in id_attr for k in ["chat", "search"]):
                            continue
                        
                        js_eval = """
                        el => {
                            let labelTxt = "";
                            if (el.id) {
                                let lbl = document.querySelector('label[for="' + el.id + '"]');
                                if (lbl) labelTxt = lbl.innerText.trim();
                            }
                            if (!labelTxt && el.getAttribute('aria-labelledby')) {
                                let lbl = document.getElementById(el.getAttribute('aria-labelledby'));
                                if (lbl) labelTxt = lbl.innerText.trim();
                            }
                            if (!labelTxt) {
                                let curr = el;
                                for (let i = 0; i < 3; i++) {
                                    if (!curr) break;
                                    let lbl = curr.querySelector('label');
                                    if (lbl) { labelTxt = lbl.innerText.trim(); break; }
                                    curr = curr.parentElement;
                                }
                            }
                            if (!labelTxt) {
                                let prev = el.previousElementSibling;
                                if (prev && prev.tagName === 'LABEL') labelTxt = prev.innerText.trim();
                            }
                            if (!labelTxt) {
                                labelTxt = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || "";
                            }
                            return labelTxt.replace(/:$/, "").trim();
                        }
                        """
                        label = el_input.evaluate(js_eval) or f"Pregunta {idx_q + 1}"
                        
                        # Filtro de renta
                        salary_kws = ["renta", "sueldo", "pretensión", "pretension", "expectativa", "salary", "monto", "monto requerido"]
                        numeric_kws = ["solo números", "solo numeros", "ingrese números", "ingrese numeros"]
                        pattern_attr = el_input.get_attribute("pattern") or ""
                        inputmode_attr = el_input.get_attribute("inputmode") or ""
                        is_salary_pattern = ("[0-9" in pattern_attr) or (inputmode_attr == "decimal")

                        maybe_salary = is_salary_pattern or any(k in label.lower() or k in ph or k in nm or k in id_attr for k in salary_kws)
                        if maybe_salary or (dom_idx == 0 and any(k in ph for k in numeric_kws)):
                            if not detalle.get("renta_selector"):
                                if nm_orig:
                                    detalle["renta_selector"] = f"[name='{nm_orig}']"
                                elif id_orig:
                                    detalle["renta_selector"] = f"#{id_orig}"
                                detalle["renta_field_name"] = nm_orig
                                detalle["renta_field_id"]   = id_orig
                            dom_idx += 1
                            continue

                        preguntas.append({ 
                            "label":   label, 
                            "indice":  idx_q, 
                            "dom_idx": dom_idx,  # posición DOM real para fallback
                            "name":    nm_orig,  # ORIGINAL para selector CSS
                            "id":      id_orig,  # ORIGINAL para selector CSS
                            "tipo":    el_input.evaluate("el => el.tagName.toLowerCase()") 
                        })
                        idx_q += 1
                        dom_idx += 1
                    except: continue
                detalle["preguntas"] = preguntas
            except Exception as e:
                console.print(f"  [dim]⚠️ Re-detección de preguntas falló: {e}[/dim]")

        if preguntas:
            console.print(f"[dim]  → Generando {len(preguntas)} respuesta(s)...[/dim]")
            try:
                for p in preguntas:
                    label = p.get("label", "Pregunta")
                    respuesta = responder_pregunta(label, descripcion)
                    respuestas_generadas.append({
                        "pregunta": label,
                        "respuesta": respuesta,
                        "selector": p.get("selector"),
                        "indice": p.get("indice", 0),
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "dom_idx": p.get("dom_idx")
                    })
                    _pausa(0.8, 1.5)
            except Exception as e:
                console.print(f"  [red]❌ Error al generar respuestas: {e}[/red]")
                # No abortamos, dejamos que el usuario rellene manual si es necesario

        if modo_revision:
            console.print("")
            # No resumimos de nuevo ni imprimimos Panel porque main.py ya lo hizo.
            # resumen = resumir_oferta(descripcion)

            # Mostrar preguntas y respuestas de forma clara
            if respuestas_generadas:
                console.print(f"\n[bold white]{'─'*80}[/bold white]")
                console.print(f"[bold white]  📝 RESPUESTAS GENERADAS ({len(respuestas_generadas)} pregunta/s)[/bold white]")
                console.print(f"[bold white]{'─'*80}[/bold white]")
                for i, r in enumerate(respuestas_generadas, 1):
                    console.print(f"\n  [bold yellow]❓ P{i}:[/bold yellow] [yellow]{r['pregunta'][:100]}[/yellow]")
                    console.print(Panel(
                        f"[white]{r['respuesta']}[/white]",
                        border_style="green", padding=(0, 1)
                    ))
            console.print("")

            # 1. Preguntar Renta PRIMERO
            renta_valor_final = "100000"
            while True:
                renta_ingresada = input("  💰 Renta líquida esperada [ENTER = $100.000]: ").strip()
                if not renta_ingresada:
                    break
                limpia = "".join(filter(str.isdigit, renta_ingresada))
                if limpia:
                    renta_valor_final = limpia
                    break
                else:
                    console.print("  [red]⚠️ Te equivocaste, ingresa solo números o presiona ENTER para el valor por defecto.[/red]")

            console.print(f"  [dim]Renta a enviar: [bold]${int(renta_valor_final):,}[/bold][/dim]".replace(",", "."))
            console.print("")

            # 2. Edición opcional de respuestas
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
                r = respuestas_generadas[idx]
                console.print(f"  [dim]Pregunta seleccionada:[/dim] [yellow]{r['pregunta'][:100]}[/yellow]")
                nueva = input(f"  Nueva respuesta: ").strip()
                if nueva:
                    r['respuesta'] = nueva
                    console.print(f"  [green]✅ Respuesta P{idx+1} actualizada[/green]\n")
                else:
                    console.print(f"  [yellow]⚠️ Edición cancelada. Respuesta sin cambios.[/yellow]\n")

            console.print("")
            console.print("")
            while True:
                confirmacion = input("  🚀 ¿Confirmar postulación con estas respuestas? [s = Sí / n = No]: ").strip().lower()
                if confirmacion in ['s', 'n']:
                    break
                console.print(f"  [red]⚠️ Te equivocaste, ingresa 's' o 'n' (escribiste: '{confirmacion}').[/red]")

            if confirmacion != "s":
                registrar_postulacion(oferta_id, titulo, empresa, url, "saltada", json.dumps(respuestas_generadas, ensure_ascii=False))
                return "saltada"

        try:
            self.page.evaluate("""
                () => {
                    const selectors = ['flowise-chatbot', '.cookie-consent', '#open_feedback', '.modal-backdrop'];
                    selectors.forEach(sel => { const el = document.querySelector(sel); if (el) el.style.display = 'none'; });
                }
            """)

            renta_selector = detalle.get("renta_selector") or "[name='Application[salary]'], input[id='salary'], input[inputmode='decimal'], input[placeholder*='número'], input[placeholder*='Solo números'], input[placeholder*='numeros']"
            renta_el = self.page.query_selector(renta_selector)
            textareas = self.page.query_selector_all("textarea")
            
            if not renta_el and not textareas:
                console.print("  [dim]No se detecta formulario directo. Buscando botón de postulación...[/dim]")
                btn_postular = self.page.query_selector("button:has-text('Postular'), .btn-postular, .postular-btn, .button-apply")
                if btn_postular:
                    btn_postular.scroll_into_view_if_needed()
                    btn_postular.click()
                    _pausa(2, 4)
                    renta_el = self.page.query_selector(renta_selector)
                    textareas = self.page.query_selector_all("textarea")

            if renta_el:
                renta_valor = renta_valor_final if 'renta_valor_final' in locals() else "100000"
                renta_el.scroll_into_view_if_needed()
                renta_el.click()
                renta_el.fill("")
                renta_el.type(renta_valor, delay=50)
                _pausa(0.3, 0.8)

            # Buscar todos los inputs y textareas de nuevo para rellenar
            seleclor_inputs = "textarea, input[type='text'], input:not([type])"
            all_inputs = self.page.query_selector_all(seleclor_inputs)
            
            # Mapear respuestas a los elementos encontrados
            for r in respuestas_generadas:
                # 1. Prioridad máxima: ID específico del campo (case-sensitive, valor original)
                el = None
                if r.get("id"):
                    el = self.page.query_selector(f"#{r['id']}")
                # 2. Buscar por name (case-sensitive, valor original)
                if not el and r.get("name"):
                    # Escapar corchetes para selectores CSS válidos
                    safe_name = r['name'].replace('[', '\\[').replace(']', '\\]')
                    try:
                        el = self.page.query_selector(f"[name='{safe_name}']")
                    except Exception as e:
                        console.print(f"  [dim]⚠️ Selector name no válido para '{safe_name}': {e}[/dim]")
                # 3. Fallback: índice DOM real
                if not el:
                    dom_idx = r.get("dom_idx", r.get("indice", 0))
                    if dom_idx < len(all_inputs):
                        el = all_inputs[dom_idx]
                
                if el:
                    # EVITAR SOBREESCRIBIR LA RENTA SI YA SE LLENÓ
                    match_renta = False
                    el_name = el.get_attribute("name") or ""
                    el_id = el.get_attribute("id") or ""
                    if detalle.get("renta_field_name") and el_name == detalle["renta_field_name"]:
                        match_renta = True
                    elif detalle.get("renta_field_id") and el_id == detalle["renta_field_id"]:
                        match_renta = True
                    elif renta_selector:
                        try:
                            match_renta = el.evaluate("(el, sel) => el.matches(sel)", renta_selector)
                        except: pass
                    
                    if match_renta:
                        continue
                        
                    try:
                        el.scroll_into_view_if_needed()
                        el.click()
                        el.fill("")
                        txt_resp = r["respuesta"]
                        if "Error code: 403" in txt_resp: 
                            txt_resp = "Disponible para ampliar información en una entrevista."
                        for char in txt_resp: 
                            el.type(char, delay=random.randint(10, 40))
                        _pausa(0.2, 0.5)
                    except: continue

            # --- SUBIR CV ---
            if CV_PATH and os.path.exists(CV_PATH):
                try:
                    # Selectores comunes para carga de archivos en DuocLaboral/otros
                    cv_selectors = [
                        'input[type="file"]',
                        '#Search_cv',
                        '#job_application_cv',
                        '.file-upload-input'
                    ]
                    file_input = None
                    for sel in cv_selectors:
                        file_input = self.page.query_selector(sel)
                        if file_input: break
                    
                    if file_input:
                        console.print(f"  [cyan]📎 Subiendo CV desde: {CV_PATH}...[/cyan]")
                        file_input.set_input_files(CV_PATH)
                        _pausa(1, 2)
                except Exception as e:
                    console.print(f"  [yellow]⚠️ Advertencia al subir CV: {e}[/yellow]")

            _pausa(1, 2)
            submit_selector = detalle.get("submit_selector") or 'button#sendApplication.btn.btn-primary.job-apply-btn'
            btn_loc = self.page.locator(submit_selector).first
            
            if btn_loc.count() == 0:
                alternativos = ['button#sendApplication', '#sendApplication', '.job-apply-btn', 'button:has-text("Enviar postulación")']
                for sel in alternativos:
                    if self.page.locator(sel).count() > 0:
                        submit_selector = sel
                        btn_loc = self.page.locator(sel).first
                        break

            if btn_loc.count() > 0:
                btn_loc.scroll_into_view_if_needed()
                _pausa(0.2, 0.5)
                url_antes = self.page.url
                btn_loc.click(timeout=5000, force=True)
                
                # ── Verificar resultado REAL del envío ──────────────────────
                # Esperar hasta 8s para que la página reaccione
                estado = "error_desconocido"
                try:
                    # Caso 1: El servidor redirige a otra página (éxito típico)
                    self.page.wait_for_url(
                        lambda url: url != url_antes,
                        timeout=8000
                    )
                    url_ahora = self.page.url
                    # Si redirige fuera de /postular/ o /jobs/, probablemente es éxito
                    if "/postular/" not in url_ahora and "/jobs/" not in url_ahora:
                        estado = "enviada"
                    else:
                        # Misma URL o URL de oferta → revisar mensajes de error
                        estado = "error_validacion"
                except Exception:
                    pass  # No hubo redirección en 8s, revisamos la página actual
                
                if estado != "enviada":
                    _pausa(0.5, 1)
                    page_content = self.page.content()
                    
                    # Caso 2: Mensaje de éxito visible en la misma página (ej: SweetAlert, toast)
                    success_locators = [
                        self.page.locator(".swal2-success"),
                        self.page.locator(".alert-success:visible"),
                        self.page.locator("text='postulación enviada'"),
                        self.page.locator("text='Gracias por postular'"),
                        self.page.locator("text='Ya postulaste'"),
                        self.page.locator("text='Postulado'"),
                    ]
                    for loc in success_locators:
                        try:
                            if loc.count() > 0:
                                estado = "enviada"
                                break
                        except: continue
                
                if estado != "enviada":
                    # Caso 3: Errores de validación HTML5 visibles
                    error_locators = [
                        self.page.locator(".is-invalid:visible"),
                        self.page.locator(".invalid-feedback:visible"),
                        self.page.locator(".alert-danger:visible"),
                        self.page.locator(".swal2-error"),
                    ]
                    tiene_error = False
                    for loc in error_locators:
                        try:
                            if loc.count() > 0:
                                tiene_error = True
                                break
                        except: continue
                    
                    if tiene_error:
                        estado = "error_validacion"
                        console.print("  [red]❌ Error de validación detectado en el formulario[/red]")
                        # Guardar HTML para diagnóstico
                        try:
                            fname = f"error_duoclaboral_{oferta_id}_{int(time.time())}.html"
                            with open(fname, "w", encoding="utf-8") as f:
                                f.write(self.page.content())
                            console.print(f"  [dim]HTML de error guardado en: {fname}[/dim]")
                        except: pass
                    else:
                        # Sin error visible ni mensaje de éxito: asumir enviada si la URL cambió
                        url_ahora = self.page.url
                        if url_ahora != url_antes:
                            estado = "enviada"
                        else:
                            # Misma URL sin errores visibles → ambiguo, marcamos error por precaución
                            estado = "error_desconocido"
                            console.print("  [yellow]⚠️ No se pudo confirmar si la postulación fue enviada (misma URL, sin errores visibles)[/yellow]")
                            try:
                                fname = f"error_duoclaboral_{oferta_id}_{int(time.time())}.html"
                                with open(fname, "w", encoding="utf-8") as f:
                                    f.write(self.page.content())
                                console.print(f"  [dim]HTML guardado en: {fname}[/dim]")
                            except: pass

                if estado == "enviada":
                    print("  ✅ Postulación CONFIRMADA — página redirigida o mensaje de éxito detectado")
                elif estado == "error_validacion":
                    print("  ❌ POSTULACIÓN FALLIDA — el formulario reportó errores de validación")
                else:
                    print("  ⚠️  Estado de postulación INCIERTO — revisa el HTML de error guardado")
            else:
                print("  ⚠️  No se encontró el botón de envío")
                estado = "error_boton"

        except Exception as e:
            print(f"  ❌ Error al rellenar/enviar: {e}")
            estado = "error"

        registrar_postulacion(oferta_id, titulo, empresa, url, estado, json.dumps(respuestas_generadas, ensure_ascii=False))
        return estado
