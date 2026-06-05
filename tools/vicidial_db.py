import logging
import socket
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "192.168.50.121",
    "user": "lhernandez",
    "password": "lhernandez10",
    "database": "asterisk",
    "connect_timeout": 5,
    "charset": "utf8mb4",
}


def _get_local_ip() -> str:
    """Devuelve la IP local del equipo."""
    return socket.gethostbyname(socket.gethostname())


def actualizar_actividad(actividad: str) -> None:
    """
    Actualiza el campo 'actividad' del agente en agentesDepuracion
    según la IP del equipo donde corre el agente.
    Valores comunes: 'Tipificando', 'Encendido', 'Apagado', 'Llamando'.
    """
    ip = _get_local_ip()
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE agentesDepuracion SET actividad = %s WHERE ip = %s",
                    (actividad, ip)
                )
            conn.commit()
        logger.info(f"[VicidialDB] Actividad actualizada a '{actividad}' para IP {ip}")
    except Exception as e:
        logger.error(f"[VicidialDB] Error al actualizar actividad: {e}")


def actualizar_status(status: int) -> None:
    """
    Actualiza el campo 'status' del agente en agentesDepuracion.
    1 = activo, 0 = inactivo.
    """
    ip = _get_local_ip()
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE agentesDepuracion SET status = %s WHERE ip = %s",
                    (status, ip)
                )
            conn.commit()
        logger.info(f"[VicidialDB] Status actualizado a '{status}' para IP {ip}")
    except Exception as e:
        logger.error(f"[VicidialDB] Error al actualizar status: {e}")


def actualizar_running(running: int) -> None:
    """
    Actualiza el campo 'running' del agente en agentesDepuracion.
    1 = agente corriendo, 0 = detenido.
    """
    ip = _get_local_ip()
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE agentesDepuracion SET running = %s WHERE ip = %s",
                    (running, ip)
                )
            conn.commit()
        logger.info(f"[VicidialDB] Running actualizado a '{running}' para IP {ip}")
    except Exception as e:
        logger.error(f"[VicidialDB] Error al actualizar running: {e}")


class VicidialDatabase:
    """Consultas generales al CRM/BD de Asterisk."""

    def consultar_cliente_por_telefono(self, telefono: str) -> str:
        """
        Busca el perfil de un cliente a partir de su número de teléfono.
        Parámetros obligatorios:
          - telefono (str): El número sin espacios ni guiones, ej. '5512345678'.
        """
        logger.info(f"[VicidialDB] Consulta por teléfono: {telefono}")
        telefono = str(telefono).replace(" ", "").replace("-", "")
        try:
            conn = pymysql.connect(**DB_CONFIG)
            with conn:
                with conn.cursor(DictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM vicidial_list WHERE phone_number = %s LIMIT 1",
                        (telefono,)
                    )
                    row = cursor.fetchone()
            if row:
                return (
                    f"Registro CRM: Nombre={row.get('first_name','')} {row.get('last_name','')}, "
                    f"Estado={row.get('status','')}, Lead ID={row.get('lead_id','')}"
                )
            return f"No se encontró registro para el teléfono {telefono}."
        except Exception as e:
            logger.error(f"[VicidialDB] Error al consultar teléfono: {e}")
            return f"Error al consultar la base de datos: {e}"
