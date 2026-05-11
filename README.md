# 🎙️ Vicidial Voice Agent: Andrea/Liliana (PRO)

Agente de Voz inteligente impulsado por **Gemini 2.0 Flash Live** para entornos de Call Center con **Vicidial**. Especializado en retención de clientes (Izzi) con lógica de cierre diferido y logueo robusto.

---

## 📁 Estructura del Proyecto

El proyecto sigue una arquitectura modular para facilitar su mantenimiento y escalabilidad:

-   `main.py`: Punto de entrada principal. Orquesta el arranque del sistema.
-   `src/`: Núcleo del agente.
    -   `agent_core.py`: Motor principal que conecta con Gemini y maneja el flujo.
    -   `audio_recorder.py`: Sistema de grabación dual (Usuario e IA).
    -   `vad_processor.py`: Detector de actividad de voz (Silero VAD).
    -   `audio_interfaces/`: Manejadores de hardware de sonido (PyAudio).
-   `tools/`: Herramientas de integración.
    -   `vicidial_api.py`: Cliente robusto para la Agent API de Vicidial.
    -   `vicidial_db.py`: Conector de base de datos para consulta de clientes.
    -   `knowledge_rag.py`: Motor de búsqueda semántica de políticas.
    -   `dispatcher.py`: Orquestador de llamadas a funciones desde la IA.
-   `config/`: Ajustes del sistema.
    -   `voice_config.json`: Perfiles de voz, guiones, reglas de negocio y credenciales.

---

## 🛰️ Integración con Vicidial (Modo Robusto)

Para conectar el agente a tu servidor Vicidial de forma profesional, sigue estos pasos:

### 1. Configuración de Credenciales
Edita `config/voice_config.json` con los datos de tu campaña:
```json
"vicidial_api": {
    "host": "IP_DE_TU_SERVIDOR",
    "user": "6666",
    "password": "PASSWORD_API",
    "agent_user": "USER_ID",
    "phone_login": "PHONE_EXT",
    "phone_pass": "PHONE_PASS",
    "campaign_id": "TU_CAMPAÑA"
}
```

### 2. Protocolo de Logueo
El script ejecuta automáticamente un **External Login** al iniciar. Esto asegura que:
1.  El agente se registre en la campaña.
2.  El servidor reconozca la sesión activa.
3.  Esté listo para disparar (`external_dial`) o recibir llamadas en modo auto-dial.

### 3. Audio en Producción
Para entornos de servidor sin tarjeta de sonido física:
-   Usa **Virtual Audio Cable** o **ALSA Loopback** para que el script capture el audio del canal SIP.
-   Alternativamente, integra un backend SIP (como `pjsua2`) en `src/audio_interfaces/`.

---

## 🧠 Capacidades Avanzadas

### ⏳ Cierre Diferido y Arrepentimiento
El agente implementa una "Gracia de 5 segundos" tras la despedida. Si el cliente dice algo antes de que el script cuelgue permanentemente, el proceso se cancela de inmediato y la IA retoma la conversación.

### 🐕 Watchdog de Conexión
Un monitor en segundo plano consulta el API de Vicidial cada 3 segundos. Si la llamada se pierde externamente (el cliente cuelga su terminal física), el script detecta el cambio de estado y libera los recursos de audio.

### 💰 Lógica de Retención Izzi
Configurado para indagar motivos, ofrecer beneficios escalonados y generar folios de cancelación únicos solo como último recurso.

---

## 🚀 Instalación y Uso

1. Instalar dependencias: `pip install -r requirements.txt`
2. Configurar el API Key en `.env`: `GEMINI_API_KEY=tu_clave_aqui`
3. Arrancar el agente con el modo deseado:

### Modos de Conversación

| Entorno | Voz | Comando |
| :--- | :--- | :--- |
| **Local** | Híbrido (IA + Pregrabados) ⭐ | `python main.py --campania <nombre>` |
| **Local** | Live (100% IA) | `python main.py --campania <nombre> --voice live` |
| **Producción Vicidial** | Híbrido (IA + Pregrabados) ⭐ | `python main.py --campania <nombre> --mode produccion` |
| **Producción Vicidial** | Live (100% IA) | `python main.py --campania <nombre> --mode produccion --voice live` |

### Grabación / Actualización de Audios

Edita el `.txt` en `config/textos_audios_<campaña>/` y ejecuta:

| Objetivo | Comando |
| :--- | :--- |
| **Grabar un audio** | `python main.py --campania <nombre> --voice grabacion --txt <nombre_archivo>` |
| **Grabar todos los audios** | `python main.py --campania <nombre> --voice grabacion --txt 1` |

---
> [!IMPORTANT]
> **Seguridad**: Asegúrate de que el acceso a `agc/api.php` esté restringido por IP en tu servidor Asterisk/Vicidial.
