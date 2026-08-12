"""
Tools del agente de voz para la Campaña Retención 2 (Simulación Ficticia Exclusiva)
===================================================================================
Este módulo proporciona las herramientas de datos ficticios ricos, atención a escenarios
de retención (cobro no reconocido, streaming, mudanza, costo, fallas técnicas) y registro
de llamadas en archivos JSON persistentes.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("Retencion2Tools")

_TOOLS_DIR = Path(__file__).parent
_PROJECT_DIR = _TOOLS_DIR.parent.parent
REGISTROS_DIR = _PROJECT_DIR / "assets" / "retencion_2" / "registro_de_llamadas"

# ---------------------------------------------------------------------------
# Perfiles de Datos Ficticios (3 Escenarios Posibles)
# ---------------------------------------------------------------------------

PROFILES = [
    {
        "perfil_id": 1,
        "titular": "Juan Carlos Pérez Gómez",
        "tipo_paquete_izzi": "izzi 60 Megas Dual Play (Internet + Telefonía)",
        "internet_megas": "60 Megas Simétricos",
        "saldo": "$540.00 MXN",
        "saldo_vencido": "$0.00 MXN (Al corriente)",
        "dia_de_pago": "Día 05 de cada mes",
        "ultima_factura": "$540.00 MXN (Facturada el 05 de este mes)",
        "contrato_forzoso": "Sin plazo forzoso (Concluido hace 6 meses)",
        "items_facturacion": [
            "Internet izzi 60M ($450/mes)",
            "Telefonía Ilimitada México/EUA/Canadá ($90/mes)",
            "ViX Premium incluido (12 meses de regalo por lealtad)"
        ],
        "escenarios_recomendados": "Costo elevado, ya no lo usa, o baja de servicio de internet"
    },
    {
        "perfil_id": 2,
        "titular": "María Elena Rodríguez Morales",
        "tipo_paquete_izzi": "izzi 100 Megas Triple Play HD (Internet + TV HD + Telefonía)",
        "internet_megas": "100 Megas",
        "saldo": "$890.00 MXN",
        "saldo_vencido": "$0.00 MXN (Al corriente)",
        "dia_de_pago": "Día 15 de cada mes",
        "ultima_factura": "$890.00 MXN (Facturada el 15 del mes anterior)",
        "contrato_forzoso": "Con Plazo Vigente (Restan 4 meses de contrato)",
        "items_facturacion": [
            "Internet izzi 100M ($590/mes)",
            "izzi tv+ HD con Decodificador Android ($180/mes)",
            "Add-on Netflix Estándar ($219/mes)",
            "ViX Premium sin costo",
            "Max (HBO) sin costo promocional"
        ],
        "escenarios_recomendados": "Aclaración de cobro no reconocido o cancelación exclusiva de streaming (Netflix/Max)"
    },
    {
        "perfil_id": 3,
        "titular": "Roberto Carlos Mendoza Sánchez",
        "tipo_paquete_izzi": "izzi 200 Megas Unlimited HD (Internet 200M + 2 Cajas Smart izzi tv+)",
        "internet_megas": "200 Megas High Speed",
        "saldo": "$1,250.00 MXN",
        "saldo_vencido": "$350.00 MXN (1 mes con adeudo pendiente)",
        "dia_de_pago": "Día 25 de cada mes",
        "ultima_factura": "$1,600.00 MXN (Incluye $350 de recargo de mes anterior)",
        "contrato_forzoso": "Sin plazo forzoso (Plazo concluido)",
        "items_facturacion": [
            "Internet izzi 200M ($850/mes)",
            "2 Cajas Smart izzi tv+ ($300/mes)",
            "Add-on Disney+ Premium ($249/mes)",
            "ViX Premium"
        ],
        "escenarios_recomendados": "Fallas técnicas recurrentes, saldo vencido / bonificación, o cambio de residencia"
    }
]


# ---------------------------------------------------------------------------
# Tools públicas para Gemini
# ---------------------------------------------------------------------------

def obtener_datos_cliente(cuenta: str = "90175351") -> dict:
    """
    Obtiene la información ficticia completa de la cuenta dictada por el cliente.
    Asigna de forma dinámica uno de los 3 perfiles ficticios con saldo, megas, día de pago,
    contrato forzoso, última factura e items de facturación con streaming.
    
    Args:
        cuenta: Número de cuenta dictado por el cliente (ej: "90175351").
    """
    clean_acc = "".join([c for c in str(cuenta) if c.isdigit()]) or "90175351"
    profile_idx = sum([int(d) for d in clean_acc]) % len(PROFILES)
    selected_profile = dict(PROFILES[profile_idx])
    selected_profile["cuenta"] = clean_acc

    logger.info(f"📊 [Retencion2] Datos cargados para cuenta {clean_acc} -> Perfil {selected_profile['perfil_id']} ({selected_profile['titular']})")
    return {
        "status": "ok",
        "datos": selected_profile,
        "message": f"Datos cargados exitosamente para la cuenta {clean_acc}."
    }


def agendar_visita_tecnica(cuenta: str, fecha_visita: str, horario_turno: str, motivo_reporte: str) -> dict:
    """
    Agenda una visita de soporte técnico especializada en el domicilio del cliente sin costo
    y aplica una bonificación de 3 días de servicio de regalo en la siguiente factura.
    
    Args:
        cuenta: Número de cuenta del cliente.
        fecha_visita: Fecha deseada (ej: "Mañana" o "14 de agosto").
        horario_turno: Turno preferido ("Mañana 9:00 - 13:00" o "Tarde 14:00 - 18:00").
        motivo_reporte: Descripción breve del fallo (ej: "Lentitud de internet", "Falla de señal tv").
    """
    logger.info(f"🛠️ [Retencion2] Cita técnica agendada para cuenta {cuenta}: {fecha_visita} ({horario_turno}) - Motivo: {motivo_reporte}")
    return {
        "status": "ok",
        "folio_visita": f"VT-{datetime.now().strftime('%M%S')}-IZZI",
        "fecha": fecha_visita,
        "horario": horario_turno,
        "bonificacion_aplicada": "3 días de bonificación sin costo acreditados a la cuenta",
        "message": f"Visita técnica programada con éxito para el {fecha_visita} en el turno {horario_turno}. Se aplicó la bonificación de 3 días sin costo."
    }


def aplicar_descuento_retencion(cuenta: str, porcentaje_descuento: int = 20, meses_duracion: int = 6) -> dict:
    """
    Aplica una promoción de retención exclusiva en la cuenta del cliente (ej. 20% de descuento por 6 o 12 meses,
    o aumento temporal de megas gratis).
    
    Args:
        cuenta: Número de cuenta del cliente.
        porcentaje_descuento: Porcentaje de descuento ofrecido (ej: 20%).
        meses_duracion: Duración de la promoción en meses (ej: 6 o 12).
    """
    logger.info(f"🎁 [Retencion2] Descuento de retención aplicado a {cuenta}: {porcentaje_descuento}% por {meses_duracion} meses.")
    return {
        "status": "ok",
        "folio_promocion": f"RET-{datetime.now().strftime('%S%f')[:4]}",
        "porcentaje_descuento": f"{porcentaje_descuento}%",
        "duracion_meses": meses_duracion,
        "message": f"Promoción de retención del {porcentaje_descuento}% de descuento por {meses_duracion} meses activada correctamente en la cuenta."
    }


def modificar_servicios_streaming(cuenta: str, servicio_streaming: str, accion: str = "cancelar_addon") -> dict:
    """
    Modifica o remueve únicamente una suscripción/add-on de streaming (ej. Netflix, Max, Disney+) 
    manteniendo el servicio base de izzi intacto.
    
    Args:
        cuenta: Número de cuenta del cliente.
        servicio_streaming: Nombre del servicio a modificar (ej: "Netflix", "Disney+", "Max").
        accion: "cancelar_addon" o "mantener_base".
    """
    logger.info(f"📺 [Retencion2] Modificación de streaming en {cuenta}: {accion} para {servicio_streaming}")
    return {
        "status": "ok",
        "servicio": servicio_streaming,
        "accion_realizada": f"Suscripción a {servicio_streaming} removida exitosamente. El paquete base de izzi se mantiene activo sin penalización.",
        "message": f"Se canceló únicamente el add-on de {servicio_streaming}. El recibo izzi se ajustará a la baja automáticamente."
    }


def solicitar_cambio_domicilio(cuenta: str, fecha_mudanza: str = "Próxima semana") -> dict:
    """
    Registra la solicitud de transferencia/cambio de domicilio sin costo de reubicación de equipos.
    
    Args:
        cuenta: Número de cuenta del cliente.
        fecha_mudanza: Fecha o periodo estimado de mudanza.
    """
    logger.info(f"🏠 [Retencion2] Solicitud de cambio de domicilio para cuenta {cuenta} en fecha {fecha_mudanza}")
    return {
        "status": "ok",
        "folio_mudanza": f"MUD-{datetime.now().strftime('%H%M%S')}",
        "costo_reubicacion": "$0.00 MXN (Cortesía de retención)",
        "message": "Solicitud de cambio de domicilio registrada sin costo de reubicación. Un técnico se pondrá en contacto para validar la nueva dirección."
    }


def guardar_registro_llamada_retencion_2(
    cuenta: str,
    cliente_nombre: str,
    motivo_principal: str,
    resultado_llamada: str,
    herramientas_ejecutadas: str = "ninguna",
    resumen_detallado: str = ""
) -> dict:
    """
    Registra el resumen y la bitácora completa de lo sucedido en la llamada en un archivo JSON persistente
    en assets/retencion_2/registro_de_llamadas/retencion_2_YYYYMMDD.json.
    
    Args:
        cuenta: Número de cuenta del cliente.
        cliente_nombre: Nombre del cliente o titular.
        motivo_principal: Motivo por el cual llamó/canceló (ej: "Cobro no reconocido", "Costo muy alto", "Falla técnica", "Cancelación streaming", "Información de saldo").
        resultado_llamada: Estatus final ("RETENIDO", "NO RETENIDO", "INFORMACION", "VISITA_TECNICA", "CAMBIO_DOMICILIO").
        herramientas_ejecutadas: Lista o texto de herramientas utilizadas durante la atención.
        resumen_detallado: Resumen de lo acordado con el cliente.
    """
    try:
        REGISTROS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"retencion_2_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = REGISTROS_DIR / filename

        registros_previos = []
        if filepath.exists():
            try:
                registros_previos = json.loads(filepath.read_text(encoding="utf-8"))
            except Exception:
                registros_previos = []

        nuevo_registro = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cuenta": cuenta,
            "cliente_nombre": cliente_nombre,
            "motivo_principal": motivo_principal,
            "resultado_llamada": resultado_llamada,
            "herramientas_ejecutadas": herramientas_ejecutadas,
            "resumen_detallado": resumen_detallado
        }

        registros_previos.append(nuevo_registro)
        filepath.write_text(json.dumps(registros_previos, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"💾 [Retencion2] Registro guardado en {filepath.name} para la cuenta {cuenta} | Estatus: {resultado_llamada}")
        return {"status": "ok", "file": str(filepath.name), "registro": nuevo_registro}
    except Exception as e:
        logger.error(f"❌ [Retencion2] Error al guardar registro JSON: {e}")
        return {"status": "error", "message": str(e)}


# Aliases de compatibilidad
limpiar_senales = lambda: {"status": "ok"}
limpiar_senales_rpa = limpiar_senales
generar_caso_negocio_siebel = lambda cuenta, tipo_caso: {"status": "ok"}
guardar_cuenta_cliente = lambda cuenta: {"status": "ok"}
guardar_telefono_cliente = lambda tel: {"status": "ok"}
guardar_nombre_cliente = lambda nom: {"status": "ok"}
guardar_tipo_cancelacion = lambda tipo: {"status": "ok"}
guardar_motivo_cancelacion = lambda mot: {"status": "ok"}
