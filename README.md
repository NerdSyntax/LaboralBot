# LaboralBot

Asistente de terminal para la automatización de postulaciones laborales mediante Inteligencia Artificial (Groq).

## Funcionalidades
- **Perfil Dinámico**: El bot aprende de tu experiencia para responder preguntas en portales.
- **Soporte Multi-portal**: Compatible con DuocLaboral, ChileTrabajos y Get on Board.
- **IA de Respuesta**: Genera respuestas personalizadas basadas en tu trayectoria real.
- **Historial**: Registro de postulaciones y respuestas enviadas.

## Instalación
1. Instalar dependencias: `pip install -r requirements.txt`
2. Instalar navegador: `playwright install chromium`
3. Ejecutar: `python main.py`

## Requisitos
- **Groq API Key**: Necesaria para el procesamiento de lenguaje natural.
- **Credenciales**: Email y contraseña de los portales a utilizar.
- **CV**: Archivo PDF con tu currículum.

## Seguridad
Las credenciales se almacenan localmente en un archivo `.env`. No se envían a servidores externos ni se deben incluir en repositorios públicos.
