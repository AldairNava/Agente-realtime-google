import logging
import socket
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "192.168.50.61",
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
    Actualiza el campo 'actividad' del agente en agentesDepuracion (Mock).
    """
    ip = _get_local_ip()
    logger.info(f"[VicidialDB] MOCK: Actividad actualizada a '{actividad}' para IP {ip}")


def actualizar_status(status: int) -> None:
    """
    Actualiza el campo 'status' del agente en agentesDepuracion (Mock).
    """
    ip = _get_local_ip()
    logger.info(f"[VicidialDB] MOCK: Status actualizado a '{status}' para IP {ip}")


def actualizar_running(running: int) -> None:
    """
    Actualiza el campo 'running' del agente en agentesDepuracion (Mock).
    """
    ip = _get_local_ip()
    logger.info(f"[VicidialDB] MOCK: Running actualizado a '{running}' para IP {ip}")


class VicidialDatabase:
    """Consultas generales al CRM/BD de Asterisk (Mock)."""

    def consultar_cliente_por_telefono(self, telefono: str) -> str:
        """
        Busca el perfil de un cliente a partir de su número de teléfono (Mock).
        """
        logger.info(f"[VicidialDB] MOCK: Consulta por teléfono: {telefono}")
        telefono = str(telefono).replace(" ", "").replace("-", "")
        return f"MOCK CRM: No se encontró registro en base de datos para el teléfono {telefono}."
