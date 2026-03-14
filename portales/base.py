from abc import ABC, abstractmethod
from playwright.sync_api import Page, BrowserContext

class PortalBase(ABC):
    """Interfaz base para todos los portales de empleo."""
    
    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context

    @abstractmethod
    def login(self) -> bool:
        """Inicia sesión en el portal."""
        pass

    def _guardar_sesion(self):
        """Guarda las cookies de la sesión actual."""
        import json
        from config import SESSION_PATH
        try:
            cookies = self.context.cookies()
            with open(SESSION_PATH, 'w') as f:
                json.dump({"cookies": cookies}, f)
            print("💾 Sesión guardada para futuros usos (evita login robótico).")
        except Exception as e:
            print(f"⚠️ Error al guardar sesión: {e}")

    @abstractmethod
    def obtener_ofertas(self, paginas: int = 3) -> list[dict]:
        """Extrae la lista básica de ofertas (título, url, id)."""
        pass

    @abstractmethod
    def obtener_detalle_oferta(self, url: str) -> dict:
        """Extrae el detalle de una oferta (descripción, preguntas, selectores)."""
        pass

    @abstractmethod
    def aplicar_filtros_avanzados(self, carrera: str, region: str):
        """Aplica filtros de búsqueda (carrera, ubicación, etc)."""
        pass

    def safe_goto(self, url: str, timeout: int = 60000, wait_until: str = "load"):
        """Navegación con reintento básico y manejo de errores."""
        try:
            self.page.goto(url, timeout=timeout, wait_until=wait_until)
        except Exception as e:
            print(f"⚠️ Error navegando a {url}: {e}")
            # Reintento simple
            try:
                self.page.goto(url, timeout=timeout + 30000, wait_until="commit")
            except:
                pass

    def wait_for_selector_safe(self, selector: str, timeout: int = 10000) -> bool:
        """Espera un selector y retorna éxito, sin lanzar excepción."""
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False
