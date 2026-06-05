"""
Tools del agente de voz para la campaña PlataCard
=================================================
Estas herramientas son llamadas por el agente de Gemini para registrar
los datos del CRM y el código de confirmación del cliente a través
de archivos de señal TXT en el directorio compartido de RPA.

Directorio de señales: <raiz_proyecto>/assets/plata/rpa_signals/
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Rutas de directorios
_TOOLS_DIR = Path(__file__).parent
_PROJECT_DIR = _TOOLS_DIR.parent
SIGNALS_DIR = _PROJECT_DIR / "assets" / "plata" / "rpa_signals"


def _write_signal(filename: str, content: str) -> dict:
    """Escribe un archivo de señal en el directorio compartido de PlataCard."""
    try:
        SIGNALS_DIR.mkdir(exist_ok=True, parents=True)
        signal_path = SIGNALS_DIR / filename
        signal_path.write_text(content.strip(), encoding="utf-8")
        logger.info(f"📤 [PlataTools] Señal '{filename}' escrita: {content.strip()}")
        return {"status": "ok", "signal": filename, "value": content.strip()}
    except Exception as e:
        logger.error(f"❌ [PlataTools] Error escribiendo señal '{filename}': {e}")
        return {"status": "error", "message": str(e)}


def crm_llenado(
    nombre: str,
    nacimiento: str,
    rfc: str,
    ingresos: str,
    ocupacion: str,
    linea: str,
    direccion: str,
    telefono: str
) -> dict:
    """
    Envía los datos recolectados del cliente al CRM y genera las señales para el RPA.

    Args:
        nombre: Nombre completo del cliente (ej: "JUAN PEREZ LOPEZ").
        nacimiento: Fecha de nacimiento en formato DD/MM/AAAA (ej: "15/08/1990").
        rfc: RFC o los primeros 10 dígitos de la CURP.
        ingresos: Ingresos mensuales aproximados (solo números, ej: "15000").
        ocupacion: Ocupación del cliente (ej: "Empleado").
        linea: Monto de línea de crédito deseada (solo números, ej: "20000").
        direccion: Dirección completa de entrega de la tarjeta.
        telefono: Número de celular confirmado del cliente (10 dígitos).

    Returns:
        dict con status e indicación de éxito.
    """
    logger.info(f"📝 [PlataTools] crm_llenado invocado para: {nombre} | Tel: {telefono}")

    # Guardar en archivos de señal individuales para compatibilidad con el RPA
    _write_signal("nombre.txt", nombre)
    _write_signal("nacimiento.txt", nacimiento)
    _write_signal("rfc.txt", rfc)
    _write_signal("ingresos.txt", ingresos)
    _write_signal("ocupacion.txt", ocupacion)
    _write_signal("linea.txt", linea)
    _write_signal("direccion.txt", direccion)
    _write_signal("telefono.txt", telefono)

    # Guardar también un JSON unificado
    try:
        SIGNALS_DIR.mkdir(exist_ok=True, parents=True)
        json_path = SIGNALS_DIR / "crm_datos.json"
        datos = {
            "nombre": nombre,
            "nacimiento": nacimiento,
            "rfc": rfc,
            "ingresos": ingresos,
            "ocupacion": ocupacion,
            "linea": linea,
            "direccion": direccion,
            "telefono": telefono
        }
        json_path.write_text(json.dumps(datos, indent=4, ensure_ascii=False), encoding="utf-8")
        logger.info(f"💾 [PlataTools] crm_datos.json guardado con éxito.")
    except Exception as e:
        logger.error(f"❌ [PlataTools] Error guardando crm_datos.json: {e}")

    return {
        "status": "success",
        "message": "Datos de CRM guardados e ingresados al sistema. Se ha enviado un código de verificación de 4 dígitos vía WhatsApp al celular del cliente. Por favor, pídale este código de 4 dígitos al cliente para continuar."
    }


def codigo_txt(codigo: str) -> dict:
    """
    Envía el código de confirmación del cliente al RPA para procesar la aprobación.

    Args:
        codigo: Código de 4 dígitos enviado al WhatsApp del cliente (ej: "1234").

    Returns:
        dict con status e indicación de éxito.
    """
    logger.info(f"🔑 [PlataTools] codigo_txt invocado con código: {codigo}")
    
    # Escribir código en archivo de señal
    result = _write_signal("codigo.txt", str(codigo))
    
    if result["status"] == "error":
        return {"status": "error", "message": f"No se pudo guardar el código: {result['message']}"}

    return {
        "status": "success",
        "message": "Código de confirmación ingresado correctamente en el sistema. Solicite al cliente que espere unos segundos mientras finaliza la validación."
    }


def limpiar_senales_plata() -> dict:
    """
    Elimina todas las señales pendientes del directorio rpa_signals de PlataCard.
    Llamar al terminar cada llamada para dejar el RPA listo para la siguiente.

    Returns:
        dict con status "ok" y cantidad de archivos eliminados.
    """
    try:
        if SIGNALS_DIR.exists():
            eliminados = []
            for f in SIGNALS_DIR.glob("*"):
                if f.is_file():
                    f.unlink()
                    eliminados.append(f.name)
            logger.info(f"🧹 [PlataTools] Señales de PlataCard limpiadas: {eliminados}")
            return {"status": "ok", "eliminados": eliminados}
        return {"status": "ok", "message": "El directorio de señales no existía."}
    except Exception as e:
        logger.error(f"❌ [PlataTools] Error limpiando señales de PlataCard: {e}")
        return {"status": "error", "message": str(e)}
