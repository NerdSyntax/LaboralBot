import random
import time
from rich.console import Console
from rich.panel import Panel
from scraper import crear_browser, login, obtener_detalle_oferta
from aplicador import postular_oferta, _pausa
from config import validar_config

console = Console()

def test_link_especifico():
    url = "https://duoclaboral.cl/trabajar-en-gandn-brands-spa/trabajos/practica-soporte-ti/820030"
    
    console.print(Panel.fit(f"[bold yellow]🧪 Prueba Específica[/bold yellow]\n[cyan]Link:[/cyan] {url}", border_style="yellow"))
    
    try:
        validar_config()
    except Exception as e:
        console.print(f"[red]❌ Error de config: {e}[/red]")
        return

    p, browser, context, page = crear_browser(headless=False)
    
    try:
        # Login
        if not login(page, context):
            console.print("[red]❌ Falló el login[/red]")
            return

        # 1. Extraer datos (Cargo, Ubicación, Resumen)
        console.print("\n[cyan]🔎 Extrayendo datos de la oferta...[/cyan]")
        detalle = obtener_detalle_oferta(page, url)
        
        # Enriquecer detalle con ubicación (detectada por JS)
        ubicacion = page.evaluate("() => document.querySelector('.ubicacion, [title*=\"Ubicación\"], .location')?.innerText || 'No detectada'")
        
        console.print(Panel(
            f"[bold cyan]Cargo:[/bold cyan] {detalle['titulo']}\n"
            f"[bold cyan]Ubicación:[/bold cyan] {ubicacion}\n"
            f"[bold cyan]Empresa:[/bold cyan] {detalle['empresa']}\n"
            f"[bold cyan]Preguntas detectadas:[/bold cyan] {len(detalle['preguntas'])}",
            title="Resumen de la Oferta"
        ))

        # 2. Postular con IA y Monto 100.000
        oferta_fake = {
            "id": "820030",
            "titulo": detalle["titulo"],
            "url": url,
            "empresa": detalle["empresa"]
        }
        
        console.print("\n[yellow]🚀 Iniciando postulación...[/yellow]")
        # modo_revision=True para que el usuario vea las respuestas antes de enviar (o lo desactivemos si prefiere)
        estado = postular_oferta(page, oferta_fake, detalle, modo_revision=True)
        
        if estado == "enviada":
            console.print("\n[green bold]✅ ¡PRUEBA EXITOSA! Postulación enviada correctamente.[/green bold]")
        else:
            console.print(f"\n[red]❌ La prueba terminó con estado: {estado}[/red]")

    except Exception as e:
        console.print(f"[red]❌ Error durante la prueba: {e}[/red]")
    finally:
        _pausa(5, 10)
        browser.close()
        p.stop()

if __name__ == "__main__":
    test_link_especifico()
