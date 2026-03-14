# LaboralBot

Asistente de terminal para la automatización de postulaciones laborales mediante Inteligencia Artificial (Groq).

## Funcionalidades
- **Perfil Dinámico**: El bot aprende de tu experiencia para responder preguntas en portales.
- **Soporte Multi-portal**: Compatible con DuocLaboral, ChileTrabajos y Get on Board.
- **IA de Respuesta**: Genera respuestas personalizadas basadas en tu trayectoria real.
- **Historial**: Registro de postulaciones y respuestas enviadas.

## Instalación Fácil (Recomendada)
Para instalar y configurar el bot automáticamente, solo necesitas tener [Python](https://www.python.org/downloads/) instalado en tu sistema.

**En Windows:**
Doble clic en el archivo `setup.bat`

**En macOS / Linux:**
Abre tu terminal y ejecuta: `bash setup.sh`

*(Esto creará un entorno virtual, instalará las dependencias de Python y descargará el navegador de Playwright automáticamente).*


## Requisitos
- **Groq API Key**: Necesaria para el procesamiento de lenguaje natural.
- **Credenciales**: Email y contraseña de los portales a utilizar.
- **CV**: Archivo PDF con tu currículum.

## Seguridad
Las credenciales se almacenan localmente en un archivo `.env`. No se envían a servidores externos ni se deben incluir en repositorios públicos.
