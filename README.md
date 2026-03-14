# LaboralBot

Asistente de terminal para la automatización de postulaciones laborales mediante Inteligencia Artificial (Groq).

## Funcionalidades
- **Perfil Dinámico**: El bot aprende de tu experiencia para responder preguntas en portales.
- **Soporte Multi-portal**: Compatible con DuocLaboral, ChileTrabajos y Get on Board.
- **IA de Respuesta**: Genera respuestas personalizadas basadas en tu trayectoria real.
- **Historial**: Registro de postulaciones y respuestas enviadas.

##  Cómo Empezar (Paso a Paso)

### 1. Descargar el Proyecto
Si eres un usuario nuevo, sigue estos pasos para descargar el bot desde GitHub:
1. Sube a la parte superior de esta página en GitHub.
2. Haz clic en el botón verde que dice **`<> Code`**.
3. Selecciona **`Download ZIP`**.
4. Descomprime (extrae) esa carpeta ZIP en tu escritorio o documentos.
5. Abre la carpeta que acabas de extraer.

### 2. Instalación Fácil (Recomendada)
Para instalar y configurar el bot automáticamente, solo necesitas tener [Python](https://www.python.org/downloads/) instalado en tu sistema.

**En Windows:**
Doble clic en el archivo `setup.bat` que está dentro de la carpeta.

**En macOS / Linux:**
Abre tu terminal dentro de la carpeta y ejecuta: `bash setup.sh`

*(Esto creará un entorno virtual, instalará las dependencias de Python y descargará el navegador de Playwright internamente).*

### 3. Configuración Final
Antes de iniciar el bot por primera vez:
1. El instalador habrá creado un archivo llamado `.env` (si no lo ves, copia el archivo `.env.example` y renómbralo a `.env`).
2. Abre el `.env` con el Block de Notas y pon tus correos, contraseñas y tu API Key de Groq.
3. Coloca tu currículum en formato PDF en la carpeta principal y llámalo **`mi_cv.pdf`**.

### 4. ¡Ejecutar!
- **En Windows:** Ejecuta `python main.py` en tu consola (Asegúrate de haber activado el entorno virtual si aplica: `venv\Scripts\activate`)
- **En macOS / Linux:** Ejecuta `source venv/bin/activate && python main.py`

*(Esto creará un entorno virtual, instalará las dependencias de Python y descargará el navegador de Playwright automáticamente).*


## Requisitos
- **Groq API Key**: Necesaria para el procesamiento de lenguaje natural.
- **Credenciales**: Email y contraseña de los portales a utilizar.
- **CV**: Archivo PDF con tu currículum.

## Seguridad
Las credenciales se almacenan localmente en un archivo `.env`. No se envían a servidores externos ni se deben incluir en repositorios públicos.
