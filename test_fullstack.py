import random
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from scraper import crear_browser, login, obtener_detalle_oferta
from aplicador import postular_oferta, _pausa
from config import validar_config

console = Console()

def test_full_stack():
    # URL proporcionada por el usuario
    url = "https://duoclaboral.cl/trabajar-en-kabeli-spa/trabajos/desarrollador-full-stack/856396"
    
    console.print(Panel.fit(
        "[bold magenta]🚀 TEST DETALLADO: Desarrollo Full Stack[/bold magenta]\n"
        f"[dim]Link:[/dim] [link={url}]{url}[/link]", 
        border_style="magenta"
    ))
    
    try:
        validar_config()
    except Exception as e:
        console.print(f"[red]❌ Error de config (revisa el .env): {e}[/red]")
        return

    p, browser, context, page = crear_browser(headless=False)
    
    try:
        # Paso 1: Login
        console.print("\n[cyan]🔑 Paso 1: Iniciando sesión...[/cyan]")
        if not login(page, context):
            console.print("[red]❌ No se pudo loguear. Revisa tus credenciales.[/red]")
            return

        # Paso 2: Extracción de datos de la página
        console.print(f"\n[cyan]🔎 Paso 2: Navegando y extrayendo datos de:[/cyan] \n{url}")
        
        # Intentar cargar con domcontentloaded para evitar timeouts por recursos pesados
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            console.print(f"[yellow]⚠️ Advertencia en navegación: {e}. Intentando continuar...[/yellow]")

        detalle = obtener_detalle_oferta(page, url)
        
        # Detectar ubicación extra con JS para el resumen
        ubicacion = page.evaluate("() => document.querySelector('.ubicacion, [title*=\"Ubicación\"], .location')?.innerText || 'No especificada'")
        
        resumen_tabla = Table(title="Resumen Extracción Portal", border_style="cyan")
        resumen_tabla.add_column("Campo", style="bold cyan")
        resumen_tabla.add_column("Valor", style="white")
        resumen_tabla.add_row("Cargo", detalle['titulo'])
        resumen_tabla.add_row("Empresa", detalle['empresa'])
        resumen_tabla.add_row("Ubicación", ubicacion.strip())
        resumen_tabla.add_row("Preguntas", str(len(detalle['preguntas'])))
        
        console.print(resumen_tabla)

        # Paso 3: Interacción con la IA
        console.print("\n[cyan]🤖 Paso 3: Generando respuestas con la IA...[/cyan]")
        
        oferta_datos = {
            "id": "856396",
            "titulo": detalle["titulo"],
            "url": url,
            "empresa": detalle["empresa"]
        }
        
        # Usamos postular_oferta en modo_revision=True para que se detenga y muestre todo
        console.print("[dim]El bot usará el monto fijo de $100.000 para la renta.[/dim]\n")
        
        # Ejecutamos la postulación
        estado = postular_oferta(page, oferta_datos, detalle, modo_revision=True)
        
        if estado == "enviada":
            console.print("\n[green bold]✨ TEST FINALIZADO: Todo funcionó correctamente.[/green bold]")
        else:
            console.print(f"\n[yellow]⚠️ El test terminó con estado: {estado}[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Error crítico en el test: {e}[/red]")
    finally:
        console.print("\n[dim]El navegador se cerrará en 10 segundos...[/dim]")
        _pausa(10, 11)
        browser.close()
        p.stop()

if __name__ == "__main__":
    test_full_stack()
