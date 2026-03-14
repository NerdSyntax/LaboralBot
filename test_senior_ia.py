import random
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from scraper import crear_browser, login, obtener_detalle_oferta
from aplicador import postular_oferta, _pausa
from config import validar_config

console = Console()

def test_senior_ia():
    # URL compleja proporcionada por el usuario
    url = "https://duoclaboral.cl/trabajar-en-importante-empresa/trabajos/ingeniero-a-de-software-senior-en-inteligencia-artificial-ia/851196"
    
    console.print(Panel.fit(
        "[bold green]🧠 TEST COMPLEJO: Senior IA Software Engineer[/bold green]\n"
        f"[dim]URL:[/dim] {url}", 
        border_style="green"
    ))
    
    try:
        validar_config()
        # Limpiar base de datos para este ID específico para permitir re-testeo
        import sqlite3
        from config import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM postulaciones WHERE oferta_id = '851196'")
        conn.commit()
        conn.close()
        console.print("[dim]🧹 Base de datos limpiada para el ID 851196...[/dim]")
    except Exception as e:
        console.print(f"[red]❌ Error de configuración: {e}[/red]")
        return

    p, browser, context, page = crear_browser(headless=False)
    
    try:
        # 1. Login
        console.print("\n[cyan]🔑 Paso 1: Verificando sesión...[/cyan]")
        if not login(page, context):
            console.print("[red]❌ Falló el inicio de sesión.[/red]")
            return

        # 2. Extracción Detallada
        console.print(f"\n[cyan]🔎 Paso 2: Extrayendo información completa del portal...[/cyan]")
        
        # Usar domcontentloaded para rapidez y evitar cuelgues de trackers
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            console.print(f"[yellow]⚠️ Advertencia en navegación (continuando): {e}[/yellow]")

        detalle = obtener_detalle_oferta(page, url)
        
        # Mostrar resumen ejecutivo en la consola
        resumen_panel = Panel(
            f"[bold cyan]Cargo:[/bold cyan] {detalle['titulo']}\n"
            f"[bold cyan]Empresa:[/bold cyan] {detalle['empresa']}\n"
            f"[bold cyan]Ubicación:[/bold cyan] {detalle.get('ubicacion', 'No detectada')}\n"
            f"[bold cyan]Preguntas de Formulario:[/bold cyan] {len(detalle['preguntas'])}\n\n"
            f"[bold yellow]Resumen del Puesto:[/bold yellow]\n{detalle['descripcion'][:500]}...",
            title="[bold white]Datos Extraídos del Portal[/bold white]",
            border_style="blue"
        )
        console.print(resumen_panel)

        # 3. Interacción IA Interactiva
        console.print("\n[cyan]🤖 Paso 3: Generando respuestas y permitiendo revisión...[/cyan]")
        
        oferta_datos = {
            "id": "851196",
            "titulo": detalle["titulo"],
            "url": url,
            "empresa": detalle["empresa"]
        }
        
        # En aplicador.py, modo_revision=True ya maneja la interactividad.
        # Asegurémonos de que el usuario vea la pregunta y la respuesta claramente.
        
        console.print("[dim]El bot usará $100.000 como pretensión de renta fija.[/dim]\n")
        
        # Ejecutar proceso de postulación
        estado = postular_oferta(page, oferta_datos, detalle, modo_revision=True)
        
        if estado == "enviada":
            console.print("\n[green bold]🎉 ¡TEST COMPLETADO CON ÉXITO! La postulación fue enviada.[/green bold]")
        else:
            console.print(f"\n[yellow]⚠️ El test finalizó con estado: {estado}[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Error durante el test: {e}[/red]")
    finally:
        console.print("\n[dim]El navegador se cerrará en 15 segundos para que revises el resultado final...[/dim]")
        _pausa(15, 16)
        browser.close()
        p.stop()

if __name__ == "__main__":
    test_senior_ia()
