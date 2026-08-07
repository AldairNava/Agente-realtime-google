"""
Módulo de conexión a la base de datos cyber_ideas_hub (192.168.50.33)
para el almacenamiento de clientes Fallback / Callback de Retención.
"""

import logging
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "192.168.50.33",
    "user": "root",
    "password": "passroot",
    "database": "cyber_ideas_hub",
    "port": 3306,
    "connect_timeout": 5,
    "charset": "utf8mb4",
    "cursorclass": DictCursor
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS RetencionCallBack (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cuenta VARCHAR(50) NULL,
    telefono VARCHAR(20) NULL,
    nombre_cliente VARCHAR(150) NULL,
    motivo_cancelacion VARCHAR(150) NULL,
    tipo_caso VARCHAR(50) DEFAULT 'CALLBACK_PENDIENTE',
    nivel_retencion INT DEFAULT 0,
    estatus VARCHAR(30) DEFAULT 'PENDIENTE',
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def get_connection():
    """Obtiene una conexión limpia a la base de datos MySQL."""
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"❌ [FallbackDB] Error al conectar a la BD ({DB_CONFIG['host']}): {e}")
        return None


def crear_tabla_retencion_callback() -> bool:
    """Crea la tabla RetencionCallBack si no existe aún."""
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        logger.info("✅ [FallbackDB] Tabla 'RetencionCallBack' verificada/creada con éxito.")
        return True
    except Exception as e:
        logger.error(f"❌ [FallbackDB] Error al crear la tabla 'RetencionCallBack': {e}")
        return False
    finally:
        conn.close()


def guardar_cliente_fallback(
    cuenta: str = None,
    telefono: str = None,
    nombre_cliente: str = None,
    motivo_cancelacion: str = None,
    tipo_caso: str = "CALLBACK_PENDIENTE",
    nivel_retencion: int = 0,
    estatus: str = "PENDIENTE"
) -> dict:
    """
    Guarda los datos de un cliente fallback en la tabla RetencionCallBack.
    """
    conn = get_connection()
    if not conn:
        return {"status": "error", "message": "No se pudo conectar a la base de datos."}

    try:
        crear_tabla_retencion_callback()

        sql = """
        INSERT INTO RetencionCallBack 
        (cuenta, telefono, nombre_cliente, motivo_cancelacion, tipo_caso, nivel_retencion, estatus)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (cuenta, telefono, nombre_cliente, motivo_cancelacion, tipo_caso, nivel_retencion, estatus)

        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            new_id = cursor.lastrowid
        conn.commit()

        logger.info(f"💾 [FallbackDB] Cliente guardado en RetencionCallBack (ID: {new_id}, Cuenta: '{cuenta}', Caso: '{tipo_caso}')")
        return {"status": "ok", "id": new_id, "cuenta": cuenta, "tipo_caso": tipo_caso}

    except Exception as e:
        logger.error(f"❌ [FallbackDB] Error al insertar en RetencionCallBack: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()
