import json

path = r"C:\vicidial-voice-agent_multicampaña\config\retention_scripts.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

nuevos_scripts = {
    "ret_saludo_v2": {
        "category": "saludo",
        "text": "Qué tal, muy buenas tardes. Está hablando al área de retención. Mi nombre es Liliana Hernández, ¿con quién tengo el placer de hablar?",
        "tts_direction": "Di con tono muy cordial y fresco:",
        "variables": [],
        "prerecord": True
    },
    "ret_saludo_v3": {
        "category": "saludo",
        "text": "Hola, le agradezco su llamada a cuentas especiales. Soy Liliana Hernández, ¿me indica su nombre para dirigirnos, por favor?",
        "tts_direction": "Di con tono sumamente amable y resolutivo:",
        "variables": [],
        "prerecord": True
    },
    "ret_pedir_cuenta_v2": {
        "category": "sondeo",
        "text": "¿Sería tan amable de indicarme su número de cuenta o el teléfono que tiene registrado con nosotros?",
        "tts_direction": "Di con tono paciente y servicial:",
        "variables": [],
        "prerecord": True
    },
    "ret_pedir_cuenta_v3": {
        "category": "sondeo",
        "text": "Para poder ayudarle, ¿me proporciona su número de cuenta o bien el teléfono que dejó de contacto?",
        "tts_direction": "Di con tono dispuesto a ayudar:",
        "variables": [],
        "prerecord": True
    },
    "ret_pedir_titular_v2": {
        "category": "sondeo",
        "text": "¿Sería tan amable de confirmarme a nombre de quién está contratado el servicio?",
        "tts_direction": "Di con tono de validación rutinaria pero amable:",
        "variables": [],
        "prerecord": True
    },
    "ret_pedir_titular_v3": {
        "category": "sondeo",
        "text": "Solo para validar los datos, ¿me podría indicar el nombre completo de la persona titular?",
        "tts_direction": "Di con tono claro y profesional:",
        "variables": [],
        "prerecord": True
    },
    "ret_motivo_baja_v2": {
        "category": "sondeo",
        "text": "Comprendo por qué nos llama. ¿Me puede platicar un poco más sobre la razón por la cual está pensando en cancelar?",
        "tts_direction": "Di con un tono sumamente comprensivo, invitando al diálogo:",
        "variables": [],
        "prerecord": True
    },
    "ret_motivo_baja_v3": {
        "category": "sondeo",
        "text": "Claro, lo entiendo. ¿Podría explicarme a detalle qué fue lo que pasó y por qué tomó la decisión de cancelar su servicio?",
        "tts_direction": "Di con tono muy empático y de escucha activa:",
        "variables": [],
        "prerecord": True
    },
    "ret_espera_v2": {
        "category": "transicion",
        "text": "Deme un segundito en la línea. Estoy checando el sistema para ver los detalles de su cuenta y validar sus plazos. Manténgase en la llamada, por favor.",
        "tts_direction": "Di con tono ágil y asegurando atención:",
        "variables": [],
        "prerecord": True
    },
    "ret_espera_v3": {
        "category": "transicion",
        "text": "Por favor, acompáñeme un momento en la línea mientras reviso su expediente y verifico el estado de su contrato. No me vaya a colgar.",
        "tts_direction": "Di con tono cuidadoso y atento:",
        "variables": [],
        "prerecord": True
    },
    "ret_cesion_derechos_v2": {
        "category": "retencion",
        "text": "Le comento una opción extra: ¿no ha pensado en cederle su servicio a algún conocido o familiar? Así no se pierde la cuenta y podemos traspasar los derechos.",
        "tts_direction": "Di con tono casual, como ofreciendo una excelente idea espontánea:",
        "variables": [],
        "prerecord": True
    },
    "ret_cesion_derechos_v3": {
        "category": "retencion",
        "text": "Oiga, ¿y de casualidad no tendrá algún amigo o familiar al que le podamos pasar el servicio? Así hacemos un cambio de titular y no perdemos los beneficios de la cuenta.",
        "tts_direction": "Di con tono amigable y propositivo:",
        "variables": [],
        "prerecord": True
    },
    "ret_entrega_equipo_v2": {
        "category": "cierre",
        "text": "Le informo que el folio que le daré será válido por treinta días. Es indispensable que lleve su identificación oficial y todos los equipos físicos, como el módem y los controles, a una de nuestras sucursales para que quede cancelado.",
        "tts_direction": "Di con tono muy claro, con peso legal pero amable:",
        "variables": [],
        "prerecord": True
    },
    "ret_entrega_equipo_v3": {
        "category": "cierre",
        "text": "Tome en cuenta que para cerrar la cancelación por completo, tiene un máximo de treinta días para presentarse en sucursal con el módem, cables y decodificadores, además de llevar su identificación oficial.",
        "tts_direction": "Di con tono explicativo y concluyente:",
        "variables": [],
        "prerecord": True
    },
    "ret_despedida_v2": {
        "category": "cierre",
        "text": "Muchísimas gracias por su tiempo y por habernos llamado. En un momento escuchará una pequeña encuesta de calidad. Que pase muy buena tarde.",
        "tts_direction": "Di con tono muy agradecido y cálido:",
        "variables": [],
        "prerecord": True
    },
    "ret_despedida_v3": {
        "category": "cierre",
        "text": "Le agradezco mucho la paciencia durante la llamada. Al terminar, le pediría si me puede apoyar contestando una breve encuesta. Que tenga un bonito día.",
        "tts_direction": "Di con tono de sonrisa cálida y cierre amable:",
        "variables": [],
        "prerecord": True
    }
}

data["scripts"].update(nuevos_scripts)

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

print("retention_scripts.json actualizado correctamente.")
