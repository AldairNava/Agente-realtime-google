# 🦎 Guía de Gestión de Campañas - Agente Camaleónico

Esta guía explica cómo agregar nuevas campañas, modificar las existentes y utilizar los nuevos comandos del agente.

## 1. Cómo agregar una nueva campaña

Para añadir una campaña (ejemplo: `plata`), sigue estos 3 pasos:

### Paso A: Crear el archivo de guiones
Crea un archivo en `config/plata_scripts.json` con las frases que usará el agente. Puedes copiar el contenido de `amex_scripts.json` como base.

### Paso B: Registrar en `voice_config.json`
Añade un nuevo bloque en la sección `"campaigns"`:

```json
"plata": {
    "name": "Campaña Plata",
    "scripts_file": "plata_scripts.json",
    "recording_dir": "recordings/pregrabados_plata",
    "voice": { "name": "Kore", "speed": "rápido" },
    "emotion": { "base_tone": "profesional", "energy_level": "medio" },
    "vicidial_api": {
        "campaign_id": "5001",
        "phone_login": "8000",
        "phone_pass": "pass123",
        "user": "agente_plata",
        "password": "password"
    },
    "agent_instructions": {
        "role": "Eres un ejecutivo de la línea Plata...",
        "identity_rules": [ ... ],
        "conversation_flow": { ... }
    }
}
```

### Paso C: Crear la carpeta de audios (Opcional)
El sistema creará automáticamente la carpeta definida en `"recording_dir"` la primera vez que ejecuten el comando de grabación para esa campaña.

---

## 2. Comandos de Uso Frecuente

### Conversación y Pruebas
| Objetivo | Comando |
| :--- | :--- |
| **Prueba Local (Híbrida)** | `python main.py --campania amex` |
| **Prueba Local (100% Live)** | `python main.py --campania amex --voice live` |
| **Lanzar en Producción** | `python main.py --campania amex --mode produccion` |

### Grabación de Activos (Audio Router)
| Objetivo | Comando |
| :--- | :--- |
| **Grabar por ID (Recomendado)** | `python main.py --campania amex --voice grabacion --id amex_saludo` |
| **Grabar frase libre** | `python main.py --campania amex --voice grabacion --frase "Texto libre" --salida "archivo"` |

---

## 3. Notas Importantes
- **Campaña Obligatoria**: Siempre debes usar `--campania <nombre>`.
- **Precedencia de Configuración**: Los valores dentro del bloque de la campaña en `voice_config.json` siempre mandan sobre los valores globales.
- **Modo Producción**: Requiere que la IP del servidor y el puerto SIP estén correctamente configurados en el bloque `"sip_config"` global.
