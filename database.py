"""
database.py — SQLite para registro de postulaciones
"""
import sqlite3
from datetime import datetime
from config import DB_PATH
import re


def inicializar_db():
    """Crea las tablas si no existen."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS postulaciones (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            oferta_id   TEXT    UNIQUE,
            titulo      TEXT,
            empresa     TEXT,
            url         TEXT,
            estado      TEXT DEFAULT 'pendiente',
            fecha       TEXT,
            respuestas  TEXT,
            portal      TEXT
        )
    """)
    
    # Migración: Verificar si la columna portal existe, si no, agregarla
    c.execute("PRAGMA table_info(postulaciones)")
    columnas = [col[1] for col in c.fetchall()]
    if "portal" not in columnas:
        c.execute("ALTER TABLE postulaciones ADD COLUMN portal TEXT")
        conn.commit()
        
    conn.commit()
    conn.close()


def ya_postule(oferta_id: str) -> bool:
    """Devuelve True si ya postulé EXITOSAMENTE a esta oferta (o fue saltada).
    Los estados de error permiten reintentar la postulación en la siguiente sesión.
    """
    ESTADOS_BLOQUEANTES = ('enviada', 'saltada', 'duplicado')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" * len(ESTADOS_BLOQUEANTES))
    c.execute(
        f"SELECT id FROM postulaciones WHERE oferta_id = ? AND estado IN ({placeholders})",
        (oferta_id, *ESTADOS_BLOQUEANTES)
    )
    existe = c.fetchone() is not None
    conn.close()
    return existe


def registrar_postulacion(oferta_id: str, titulo: str, empresa: str,
                           url: str, estado: str, respuestas: str = "", portal: str = ""):
    """Registra una postulación en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO postulaciones
        (oferta_id, titulo, empresa, url, estado, fecha, respuestas, portal)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (oferta_id, titulo, empresa, url, estado,
          datetime.now().strftime("%Y-%m-%d %H:%M"), respuestas, portal))
    conn.commit()
    conn.close()


def listar_postulaciones() -> list[dict]:
    """Devuelve todas las postulaciones registradas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM postulaciones ORDER BY fecha DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def total_postulaciones() -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM postulaciones WHERE estado='enviada'")
        total = c.fetchone()[0]
        conn.close()
        return total
    except sqlite3.OperationalError:
        # Si la tabla no existe, inicializar y retornar 0
        inicializar_db()
        return 0


def ya_omitida(oferta_id: str) -> bool:
    """Devuelve True si esta oferta ya fue descartada/omitida en una sesión anterior."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id FROM postulaciones WHERE oferta_id = ? AND estado IN ('omitida', 'no_relevante', 'palabra_prohibida', 'experiencia_alta')",
        (oferta_id,)
    )
    existe = c.fetchone() is not None
    conn.close()
    return existe

def empresa_omitida(empresa: str) -> bool:
    """Devuelve True si la empresa fue descartada/omitida en la base de datos."""
    if not empresa or empresa == "Empresa no especificada":
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id FROM postulaciones WHERE empresa = ? AND estado IN ('omitida', 'no_relevante', 'palabra_prohibida', 'experiencia_alta') LIMIT 1",
        (empresa,)
    )
    existe = c.fetchone() is not None
    conn.close()
    return existe


def registrar_omitida(oferta_id: str, titulo: str, empresa: str, url: str, motivo: str = "omitida", portal: str = ""):
    """
    Registra una oferta descartada en la BD para no volver a evaluarla.
    motivo puede ser: 'omitida', 'no_relevante', 'palabra_prohibida'
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO postulaciones
        (oferta_id, titulo, empresa, url, estado, fecha, respuestas, portal)
        VALUES (?, ?, ?, ?, ?, ?, '', ?)
    """, (oferta_id, titulo, empresa, url, motivo, datetime.now().strftime("%Y-%m-%d %H:%M"), portal))
    conn.commit()
    conn.close()


def listar_omitidas() -> list[dict]:
    """Devuelve todas las ofertas descartadas (no relevantes, palabras prohibidas, omitidas)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM postulaciones
        WHERE estado IN ('omitida', 'no_relevante', 'palabra_prohibida')
        ORDER BY fecha DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def borrar_oferta_por_id(id_db: int):
    """Borra un registro específico de la base de datos por su ID interno."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM postulaciones WHERE id = ?", (id_db,))
    conn.commit()
    conn.close()

def borrar_todas_por_estado(estado_lista: list):
    """Borra todos los registros que coincidan con los estados de la lista."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" * len(estado_lista))
    c.execute(f"DELETE FROM postulaciones WHERE estado IN ({placeholders})", estado_lista)
    conn.commit()
    conn.close()
