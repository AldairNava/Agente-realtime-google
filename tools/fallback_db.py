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


def guardar_registro_pollution(cuenta: str, motivo: str) -> dict:
    """
    Guarda los datos de transferencia en la tabla 'pollution'.
    """
    conn = get_connection()
    if not conn:
        return {"status": "error", "message": "No se pudo conectar a la base de datos."}

    try:
        # Los campos obligatorios solicitados por el usuario
        caso = "TRANSFERENCIA"
        agente = "14080"
        status = "not found cuenta"
        resumen = "pollution agente retecion"
        
        # Validar que el motivo sea válido. Si no lo es, dejar como "OTROS" o lo que corresponda.
        # Lista de motivos válidos:
        motivos_validos = [
            "NEGOCIOS PRO", "IZZI MOVIL", "OTROS", "SERVICIOS", "MODULO", 
            "SOPORTE TECNICO", "SUPERVISOR", "COBRANZA", "FTTH", 
            "RETENCIONES", "PAGOS IVR", "DR WIFI", "TELEMARKETING"
        ]
        
        motivo_upper = str(motivo).upper().strip() if motivo else "OTROS"
        if motivo_upper not in motivos_validos:
            # Intentar ver si coincide de forma parcial, si no dejar OTROS
            coincidencia = "OTROS"
            for mv in motivos_validos:
                if mv in motivo_upper:
                    coincidencia = mv
                    break
            motivo_final = coincidencia
        else:
            motivo_final = motivo_upper

        sql = """
        INSERT INTO pollution (caso, cuenta, agente, status, resumen, motivo)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (caso, cuenta, agente, status, resumen, motivo_final)

        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            new_id = cursor.lastrowid
        conn.commit()

        logger.info(f"📊 [FallbackDB] Registro insertado en la tabla 'pollution' (ID: {new_id}, Cuenta: '{cuenta}', Motivo: '{motivo_final}')")
        return {"status": "ok", "id": new_id, "cuenta": cuenta, "motivo": motivo_final}

    except Exception as e:
        logger.error(f"❌ [FallbackDB] Error al insertar en la tabla 'pollution': {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

