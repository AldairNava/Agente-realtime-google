"""
Tools del agente de voz para el RPA de Retención izzi
======================================================
Estas herramientas son llamadas por el agente de Gemini para comunicarse
con el proceso RPA a través de archivos de señal TXT.

Directorio de señales: <raiz_proyecto>/rpa_signals/
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Ruta del directorio de señales (relativa a la raíz del proyecto)
_TOOLS_DIR   = Path(__file__).parent
_PROJECT_DIR = _TOOLS_DIR.parent
SIGNALS_DIR  = _PROJECT_DIR / "assets" / "retencion" / "rpa_signals"

# Motivos válidos aceptados por el portal (case-insensitive)
MOTIVOS_VALIDOS = [
    "Económico",
    "Cambio de Domicilio",
    "Fallas Técnicas",
    "Quejas",
    "Competencia",
    "No lo Utiliza",
    "Migración PYME",
    "Visita técnica inmediata por instalación",
]


def _write_signal(filename: str, content: str) -> dict:
    """Escribe un archivo de señal en el directorio compartido con el RPA."""
    try:
        SIGNALS_DIR.mkdir(exist_ok=True)
        signal_path = SIGNALS_DIR / filename
        signal_path.write_text(content.strip(), encoding="utf-8")
        logger.info(f"📤 [RetencionTools] Señal '{filename}' escrita: {content.strip()}")
        return {"status": "ok", "signal": filename, "value": content.strip()}
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error escribiendo señal '{filename}': {e}")
        return {"status": "error", "message": str(e)}


def _write_pollution(cuenta: str, tipo_caso: str) -> dict:
    """Escribe un archivo de señal para el RPA de Pollution (Generación de Casos de Negocio en Siebel) y registra en BD."""
    try:
        pollution_dir = Path(r"C:\pollution")
        pollution_dir.mkdir(parents=True, exist_ok=True)
        signal_path = pollution_dir / "pollution_cte.txt"
        
        # Formato: cuenta|tipo_caso
        content = f"{cuenta}|{tipo_caso}"
        signal_path.write_text(content, encoding="utf-8")
        logger.info(f"📤 [RetencionTools] Archivo pollution_cte.txt escrito en C:\\pollution: {content}")
        
        # Guardado en base de datos RetencionCallBack
        try:
            from tools.fallback_db import guardar_cliente_fallback
            tel_file = SIGNALS_DIR / "tel.txt"
            nombre_file = SIGNALS_DIR / "nombre.txt"
            motivo_file = SIGNALS_DIR / "motivo.txt"
            
            tel_val = tel_file.read_text(encoding="utf-8").strip() if tel_file.exists() else None
            nombre_val = nombre_file.read_text(encoding="utf-8").strip() if nombre_file.exists() else None
            motivo_val = motivo_file.read_text(encoding="utf-8").strip() if motivo_file.exists() else None
            
            db_res = guardar_cliente_fallback(
                cuenta=cuenta,
                telefono=tel_val,
                nombre_cliente=nombre_val,
                motivo_cancelacion=motivo_val,
                tipo_caso=tipo_caso,
                nivel_retencion=0
            )
            logger.info(f"📊 [RetencionTools] Registro guardado en BD RetencionCallBack: {db_res}")
        except Exception as db_err:
            logger.error(f"⚠️ [RetencionTools] Error al guardar en BD RetencionCallBack: {db_err}")

        return {"status": "ok", "signal": "pollution_cte.txt", "value": content}
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error escribiendo pollution_cte.txt: {e}")
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------------------------
# Tools públicas (registradas en el agente)
# ---------------------------------------------------------------------------

def guardar_cuenta_cliente(cuenta: str) -> dict:
    """
    Envía el número de cuenta del cliente al RPA para que lo busque en el portal.
    
    Args:
        cuenta: Número de cuenta del cliente (ej. "90175351").
    
    Returns:
        dict con status "ok" o "error".
    """
    if not cuenta or not str(cuenta).strip():
        return {"status": "error", "message": "El número de cuenta no puede estar vacío."}
    return _write_signal("cuenta.txt", str(cuenta))


def guardar_telefono_cliente(telefono: str) -> dict:
    """
    Envía el número de teléfono del cliente al RPA para que lo busque en el portal.
    
    Args:
        telefono: Número de teléfono del cliente (ej. "5595734105").
    
    Returns:
        dict con status "ok" o "error".
    """
    if not telefono or not str(telefono).strip():
        return {"status": "error", "message": "El número de teléfono no puede estar vacío."}
    return _write_signal("tel.txt", str(telefono))


def guardar_nombre_cliente(nombre: str) -> dict:
    """
    Envía el nombre completo del cliente al RPA para que lo busque en el portal.
    
    Args:
        nombre: Nombre completo del titular (ej. "KARINA CARDENAS ALCANTARA").
    
    Returns:
        dict con status "ok" o "error".
    """
    if not nombre or not nombre.strip():
        return {"status": "error", "message": "El nombre no puede estar vacío."}
    return _write_signal("nombre.txt", nombre)


def guardar_tipo_cancelacion(tipo: str) -> dict:
    """
    Informa al RPA si la cancelación es 'total' o 'parcial'.
    
    Args:
        tipo: "total" o "parcial".
    
    Returns:
        dict con status "ok" o "error".
    """
    tipo_lower = tipo.strip().lower()
    if tipo_lower not in ("total", "parcial"):
        return {
            "status": "error",
            "message": f"Tipo de cancelación inválido: '{tipo}'. Usa 'total' o 'parcial'."
        }
    return _write_signal("cancelacion.txt", tipo_lower)


def guardar_motivo_cancelacion(motivo: str) -> dict:
    """
    Envía el motivo de cancelación al RPA para que lo seleccione en la lista del portal.
    
    El motivo debe ser uno de los siguientes (se acepta texto similar, case-insensitive):
    - Económico
    - Cambio de Domicilio
    - Fallas Técnicas
    - Quejas
    - Competencia
    - No lo Utiliza
    - Migración PYME
    - Visita técnica inmediata por instalación
    
    Args:
        motivo: Motivo de cancelación expresado por el cliente.
    
    Returns:
        dict con status "ok" o "error".
    """
    if not motivo or not motivo.strip():
        return {"status": "error", "message": "El motivo no puede estar vacío."}
    
    # Intentar mapear al motivo más cercano
    motivo_mapeado = _mapear_motivo(motivo)
    logger.info(f"🗺️ Motivo recibido: '{motivo}' → mapeado a: '{motivo_mapeado}'")
    
    return _write_signal("motivo.txt", motivo_mapeado)


def limpiar_senales() -> dict:
    """
    Elimina todas las señales pendientes del directorio rpa_signals.
    Llamar al terminar cada llamada para dejar el RPA listo para la siguiente.
    
    Returns:
        dict con status "ok" y cantidad de archivos eliminados.
    """
    try:
        SIGNALS_DIR.mkdir(exist_ok=True)
        eliminados = []
        for f in SIGNALS_DIR.glob("*.txt"):
            f.unlink()
            eliminados.append(f.name)
        logger.info(f"🧹 [RetencionTools] Señales limpiadas: {eliminados}")
        return {"status": "ok", "eliminados": eliminados}
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error limpiando señales: {e}")
        return {"status": "error", "message": str(e)}

# Alias para compatibilidad con la definición de la herramienta
limpiar_senales_rpa = limpiar_senales


def clasificar_perfil_cuenta(datos: dict) -> dict:
    """
    Analiza la información extraída por Siebel RPA e identifica automáticamente:
    Portafolio, Tecnología (FTTH/HFC), Segmento (Residencial/Negocios) y Plazo Forzoso.
    """
    items = datos.get("items_facturacion", [])
    texto_full = " ".join([str(i) for i in items] + [str(v) for v in datos.values()]).lower()

    # 1. Portafolio
    if any(str(item).endswith(" M") or " m " in str(item).lower() for item in items):
        portafolio = "Modular / Ladrillos"
    elif "axt" in texto_full or "axtel" in texto_full:
        portafolio = "Lego Axtel"
    elif "wizz" in texto_full or "unesco" in texto_full:
        portafolio = "Wizz PM / Wizz Plus"
    elif items and not any("izzi" in str(item).lower() for item in items):
        portafolio = "Legacy / Cablevisión (Requiere 'Actualizar Oferta')"
    else:
        portafolio = "Masivo / izzi Wow"

    # 2. Tecnología
    if any(str(item).startswith("L ") or str(item).startswith("LN ") or "ftth" in str(item).lower() for item in items):
        tecnologia = "FTTH (Fibra Óptica - Migración forzosa requiere cambio de equipos)"
    else:
        tecnologia = "HFC (Coaxial)"

    # 3. Segmento
    if "negocios" in texto_full:
        segmento = "Negocios (Requiere Apoderado Legal / Acta Constitutiva)"
    else:
        segmento = "Residencial"

    # 4. Plazo Forzoso
    tiene_plazo = datos.get("plazo_vigente", False) or "plazo" in datos.get("estatus", "").lower()
    if tiene_plazo:
        plazo_status = "Con Plazo Vigente (Aplica penalización en baja anticipada)"
    else:
        plazo_status = "Sin Plazo (Apto para Renovación a 6 meses Con/Sin Beneficios)"

    reglas = []
    if "Sin Plazo" in plazo_status:
        reglas.append("Apto para Renovación de Plazo Forzoso a 6 meses.")
    if "Negocios" in segmento:
        reglas.append("No aplica Adhesión de Derechos; requiere validar Apoderado Legal.")
    if "Legacy" in portafolio:
        reglas.append("Para realizar Downsale/Downgrade primero dar clic en 'Actualizar Oferta'.")

    return {
        "portafolio": portafolio,
        "tecnologia": tecnologia,
        "segmento": segmento,
        "plazo_forzoso": plazo_status,
        "reglas_aplicables": reglas
    }


def obtener_datos_cliente() -> dict:
    """
    Obtiene los datos del cliente que fueron extraídos del portal de Siebel por el RPA.
    Llama esta herramienta cuando necesites conocer el saldo, estatus, plan o cualquier
    información detallada del cliente que ya fue buscado en el sistema.
    
    Returns:
        dict con la información del cliente, perfil_cuenta y reglas aplicables.
    """
    try:
        datos_path = SIGNALS_DIR / "datos_cliente.json"
        if datos_path.exists():
            import json
            content = datos_path.read_text(encoding="utf-8")
            datos = json.loads(content)
            
            # Clasificación automática de perfil de cuenta
            perfil = clasificar_perfil_cuenta(datos)
            datos["perfil_cuenta"] = perfil
            
            logger.info(f"📖 [RetencionTools] Datos del cliente leídos: {list(datos.keys())} | Perfil: {perfil['portafolio']} / {perfil['tecnologia']}")
            return {"status": "ok", "datos": datos}
        else:
            logger.warning("⚠️ [RetencionTools] El archivo datos_cliente.json no existe aún.")
            return {
                "status": "esperando",
                "message": (
                    "El sistema aún está cargando o buscando los datos del cliente en Siebel. "
                    "Por favor, indíquele al cliente de viva voz que está validando sus datos "
                    "y vuelva a llamar a esta herramienta en 2 o 3 segundos para obtener la información."
                )
            }
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error leyendo datos_cliente.json: {e}")
        return {"status": "error", "message": str(e)}


def generar_caso_negocio_siebel(cuenta: str, tipo_caso: str) -> dict:
    """
    Genera un caso de negocio automático en Siebel a través del RPA.
    
    Args:
        cuenta: Número de cuenta del cliente (ej. "90175351").
        tipo_caso: Tipo de caso a generar ('INFO GENERAL DEL SERV', 'TRANSFERENCIA', 'RETENIDO', 'NO RETENIDO', etc.).
    
    Returns:
        dict con status "ok" o "error".
    """
    if not cuenta or not str(cuenta).strip():
        return {"status": "error", "message": "El número de cuenta no puede estar vacío."}
    if not tipo_caso or not str(tipo_caso).strip():
        return {"status": "error", "message": "El tipo de caso no puede estar vacío."}
    
    return _write_pollution(str(cuenta).strip(), str(tipo_caso).strip())

def guardar_resumen_transferencia(cuenta: str, resumen: str) -> dict:
    """
    Guarda un resumen del motivo por el cual el cliente está siendo transferido
    cuando el agente no tiene la información o la solicitud está fuera de su alcance.
    
    Args:
        cuenta: Número de cuenta del cliente.
        resumen: Explicación breve de qué buscaba el cliente y por qué se le transfiere.
    """
    if not cuenta or not str(cuenta).strip():
        return {"status": "error", "message": "El número de cuenta no puede estar vacío."}
    
    resumen_file = SIGNALS_DIR / "resumen.txt"
    try:
        SIGNALS_DIR.mkdir(exist_ok=True)
        resumen_file.write_text(f"Cuenta: {cuenta}\nResumen: {resumen}", encoding="utf-8")
        logger.info(f"📝 [RetencionTools] Resumen de transferencia guardado para {cuenta}.")
        return {"status": "ok", "message": "Resumen guardado exitosamente."}
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error escribiendo resumen.txt: {e}")
        return {"status": "error", "message": str(e)}


def colgar_llamada_genesis() -> dict:
    """
    Envía una señal para que el RPA de Genesis cuelgue la llamada actual.
    Debe llamarse al final de la interacción.
    """
    try:
        SIGNALS_DIR.mkdir(exist_ok=True)
        colgar_file = SIGNALS_DIR / "colgar.txt"
        colgar_file.write_text("COLGAR", encoding="utf-8")
        logger.info("📞 [RetencionTools] Señal de colgado (colgar.txt) enviada al RPA de Genesis.")
        return {"status": "ok", "message": "Señal de colgado enviada."}
    except Exception as e:
        logger.error(f"❌ [RetencionTools] Error escribiendo colgar.txt: {e}")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _mapear_motivo(motivo_raw: str) -> str:
    """
    Intenta encontrar el motivo oficial más cercano al texto del cliente.
    Si no hay coincidencia, retorna el texto original para que el RPA intente.
    """
    motivo_lower = motivo_raw.strip().lower()
    
    # Mapa de palabras clave → motivo oficial
    mapping = {
        "económico":     "Económico",
        "economico":     "Económico",
        "dinero":        "Económico",
        "caro":          "Económico",
        "precio":        "Económico",
        "domicilio":     "Cambio de Domicilio",
        "mudanza":       "Cambio de Domicilio",
        "mudo":          "Cambio de Domicilio",
        "falla":         "Fallas Técnicas",
        "fallas":        "Fallas Técnicas",
        "técnica":       "Fallas Técnicas",
        "técnico":       "Fallas Técnicas",
        "problema":      "Fallas Técnicas",
        "queja":         "Quejas",
        "molesto":       "Quejas",
        "atención":      "Quejas",
        "servicio":      "Quejas",
        "competencia":   "Competencia",
        "otro":          "Competencia",
        "totalplay":     "Competencia",
        "telmex":        "Competencia",
        "utiliza":       "No lo Utiliza",
        "usa":           "No lo Utiliza",
        "necesito":      "No lo Utiliza",
        "pyme":          "Migración PYME",
        "empresa":       "Migración PYME",
        "negocio":       "Migración PYME",
        "visita":        "Visita técnica inmediata por instalación",
        "instalación":   "Visita técnica inmediata por instalación",
        "instalacion":   "Visita técnica inmediata por instalación",
        "técnico":       "Visita técnica inmediata por instalación",
    }
    
    for keyword, oficial in mapping.items():
        if keyword in motivo_lower:
            return oficial
    
    # Sin coincidencia: retornar tal cual (el RPA usará búsqueda parcial)
    return motivo_raw.strip()


# ---------------------------------------------------------------------------
# Definición de herramientas para el dispatcher del agente
# (compatible con el ToolDispatcher del proyecto)
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS = [
    {
        "name": "guardar_cuenta_cliente",
        "description": (
            "Registra el número de cuenta del cliente para buscarlo en el sistema de retención. "
            "Llama esta herramienta tan pronto como el cliente diga su número de cuenta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cuenta": {
                    "type": "string",
                    "description": "Número de cuenta del cliente (solo dígitos, ej: '90175351')."
                }
            },
            "required": ["cuenta"]
        },
        "fn": guardar_cuenta_cliente,
    },
    {
        "name": "guardar_telefono_cliente",
        "description": (
            "Registra el número de teléfono del cliente para buscarlo en el sistema de retención. "
            "Llama esta herramienta cuando el cliente no recuerde su número de cuenta y proporcione su teléfono."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "telefono": {
                    "type": "string",
                    "description": "Número de teléfono del cliente (10 dígitos)."
                }
            },
            "required": ["telefono"]
        },
        "fn": guardar_telefono_cliente,
    },
    {
        "name": "guardar_nombre_cliente",
        "description": (
            "Registra el nombre completo del titular para buscarlo en el sistema de retención. "
            "Llama esta herramienta cuando el cliente no recuerde su número de cuenta y proporcione su nombre completo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre completo del titular de la cuenta."
                }
            },
            "required": ["nombre"]
        },
        "fn": guardar_nombre_cliente,
    },
    {
        "name": "guardar_tipo_cancelacion",
        "description": (
            "Registra si el cliente quiere cancelar la totalidad de sus servicios o solo una parte. "
            "Llama esta herramienta cuando el cliente indique qué quiere cancelar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["total", "parcial"],
                    "description": "'total' si cancela todo, 'parcial' si cancela solo TV o Internet."
                }
            },
            "required": ["tipo"]
        },
        "fn": guardar_tipo_cancelacion,
    },
    {
        "name": "guardar_motivo_cancelacion",
        "description": (
            "Registra el motivo de cancelación expresado por el cliente. "
            "Llama esta herramienta cuando el cliente diga la razón por la que quiere cancelar. "
            f"Motivos reconocidos: {', '.join(MOTIVOS_VALIDOS)}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Motivo de cancelación del cliente (texto libre)."
                }
            },
            "required": ["motivo"]
        },
        "fn": guardar_motivo_cancelacion,
    },
    {
        "name": "limpiar_senales_rpa",
        "description": (
            "Limpia todas las señales del RPA al terminar la llamada. "
            "Llama esta herramienta siempre antes de colgar la llamada."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "fn": limpiar_senales,
    },
    {
        "name": "obtener_datos_cliente",
        "description": (
            "Obtiene los datos del cliente extraídos en tiempo real por el RPA desde Siebel. "
            "Úsala cuando el cliente pregunte por su saldo, su plan contratado, su estatus actual, "
            "o cuando necesites validar información cargada en el sistema."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "fn": obtener_datos_cliente,
    },
    {
        "name": "generar_caso_negocio_siebel",
        "description": (
            "Genera un caso de negocio automático en Siebel para documentar la interacción. "
            "Úsala cuando el cliente solo pide información general (tipo_caso='INFO GENERAL DEL SERV'), "
            "o cuando solicita cancelación de servicios adicionales o tiene fallas y debe ser redirigido a soporte (tipo_caso='TRANSFERENCIA'). "
            "Requiere que tengas el número de cuenta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cuenta": {
                    "type": "string",
                    "description": "Número de cuenta del cliente."
                },
                "tipo_caso": {
                    "type": "string",
                    "description": "Tipo de caso. Opciones comunes: 'INFO GENERAL DEL SERV', 'TRANSFERENCIA'."
                }
            },
            "required": ["cuenta", "tipo_caso"]
        },
        "fn": generar_caso_negocio_siebel,
    },
    {
        "name": "guardar_resumen_transferencia",
        "description": (
            "Guarda un resumen del motivo por el cual se está transfiriendo al cliente. "
            "Úsala obligatoriamente cuando el cliente pide información que no tienes o no le puedes resolver."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cuenta": {
                    "type": "string",
                    "description": "Número de cuenta del cliente."
                },
                "resumen": {
                    "type": "string",
                    "description": "Breve resumen de lo que el cliente quería y por qué se transfiere."
                }
            },
            "required": ["cuenta", "resumen"]
        },
        "fn": guardar_resumen_transferencia,
    },
    {
        "name": "colgar_llamada_genesis",
        "description": (
            "Cuelga la llamada actual enviando una señal al sistema Genesis. "
            "Úsala siempre como la ÚLTIMA herramienta para despedirte y terminar la llamada en Nivel 0."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "fn": colgar_llamada_genesis,
    },
]

