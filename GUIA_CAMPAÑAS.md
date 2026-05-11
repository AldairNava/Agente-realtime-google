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

### 🤖 Modos de Conversación (Agente Activo)

| Entorno | Voz | Comando |
| :--- | :--- | :--- |
| **Local** | Híbrido (IA + Pregrabados) ⭐ | `python main.py --campania <nombre>` |
| **Local** | Live (100% IA en tiempo real) | `python main.py --campania <nombre> --voice live` |
| **Producción Vicidial** | Híbrido (IA + Pregrabados) ⭐ | `python main.py --campania <nombre> --mode produccion` |
| **Producción Vicidial** | Live (100% IA en tiempo real) | `python main.py --campania <nombre> --mode produccion --voice live` |

> **¿Híbrido o Live?**
> - **Híbrido**: La IA usa los audios pregrabados (`.wav`) para saludos y frases fijas. Más natural y consistente. **Recomendado para producción.**
> - **Live**: La IA genera todo el audio en tiempo real con su propia voz. Más flexible, pero sin los audios personalizados.

---

### 🎙️ Grabación de Audios (Gestión de Pregrabados)

El flujo correcto es: **1) editar el `.txt` → 2) ejecutar el comando de grabación.**
Los archivos `.txt` están en `config/textos_audios_<nombre_campaña>/`.

| Objetivo | Comando |
| :--- | :--- |
| **Grabar un audio específico** | `python main.py --campania <nombre> --voice grabacion --txt <nombre_archivo>` |
| **Grabar TODOS los audios de la campaña** | `python main.py --campania <nombre> --voice grabacion --txt 1` |
| **Grabar una frase libre desde la terminal** | `python main.py --campania <nombre> --voice grabacion --frase "Texto aquí" --salida "nombre_archivo"` |

**Ejemplo para retención:**
```bash
# Solo regenerar el saludo
python main.py --campania retencion --voice grabacion --txt ret_saludo

# Regenerar todos los audios de retención de un jalón
python main.py --campania retencion --voice grabacion --txt 1
```

---

## 3. Notas Importantes
- **Campaña Obligatoria**: Siempre debes usar `--campania <nombre>`.
- **Modo Híbrido por defecto**: Si no indicas `--voice`, el agente usará el modo híbrido automáticamente.
- **Los `.txt` son la fuente de verdad**: Edita solo el `.txt` correspondiente y regenera el audio. No es necesario tocar ningún archivo JSON.
- **Modo Producción**: Requiere que la IP del servidor y el puerto SIP estén correctamente configurados en el bloque `"sip_config"` de `voice_config.json`.
