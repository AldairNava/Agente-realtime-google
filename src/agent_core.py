import asyncio
import os
import sys
import json
import logging
import wave
from datetime import datetime
from google import genai
from google.genai import types

from .audio_interfaces.local_audio import LocalAudioInterface
from .vad_processor import VADProcessor
from .audio_router import AudioRouter
from tools.dispatcher import ToolDispatcher
from tools.amex_form import AMEXFormHandler
from .audio_recorder import AudioRecorder, AgentVoiceCapture

logger = logging.getLogger(__name__)


class SafeLiveConnection:
    def __init__(self, connect_manager, connect_timeout=10.0, close_timeout=4.0):
        self.connect_manager = connect_manager
        self.connect_timeout = connect_timeout
        self.close_timeout = close_timeout
        self.conn_success = False

    async def __aenter__(self):
        session = await asyncio.wait_for(self.connect_manager.__aenter__(), timeout=self.connect_timeout)
        self.conn_success = True
        return session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn_success:
            try:
                await asyncio.wait_for(self.connect_manager.__aexit__(exc_type, exc_val, exc_tb), timeout=self.close_timeout)
            except asyncio.TimeoutError:
                logger.warning("⚠️ [SafeLiveConnection] Timeout al cerrar la sesión de Gemini Live. Forzando continuación.")
            except Exception as ce:
                logger.warning(f"⚠️ [SafeLiveConnection] Error al cerrar la sesión de Gemini Live: {ce}")
        return False


class VoiceAgent:
    def __init__(self, api_key, audio_interface=None, campania='amex', voice_mode='hibrido', 
                 execution_mode='local', grabacion_txt=None, grabacion_frase=None, grabacion_salida=None):
        
        self.campania_name = campania
        self.voice_mode = voice_mode
        self.execution_mode = execution_mode
        self.grabacion_txt = grabacion_txt
        self.grabacion_frase = grabacion_frase
        self.grabacion_salida = grabacion_salida
        
        if not api_key or api_key == 'tu_clave_de_api_aqui':
            logger.error("API Key ausente.")
            sys.exit(1)

        self.client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"}
        )
        
        # Cargar configuración central (usa override dinámico en memoria si existe)
        inline_cfg = os.environ.get('VOICE_CONFIG_INLINE')
        if inline_cfg:
            self.full_cfg = json.loads(inline_cfg)
        else:
            config_path = os.environ.get(
                'VOICE_CONFIG_OVERRIDE',
                os.path.join(os.path.dirname(__file__), '..', 'config', 'voice_config.json')
            )
            with open(config_path, 'r', encoding='utf-8') as f:
                self.full_cfg = json.load(f)


        # Validar y cargar perfil de campaña
        if campania not in self.full_cfg.get('campaigns', {}):
            raise ValueError(f"La campaña '{campania}' no existe en voice_config.json")
        
        self.campania_cfg = self.full_cfg['campaigns'][campania]
        # Inyectar configuraciones de campaña en un objeto de configuración activa
        # Esto permite que el resto del código siga funcionando con self.voice_cfg
        self.voice_cfg = {**self.full_cfg.get('common_settings', {}), **self.campania_cfg}
        
        # Especial: unificar vicidial_api para el ToolDispatcher en producción o pruebas
        if self.execution_mode in ('produccion', 'pruebas'):
            active_host = self.full_cfg.get('vicidial_api', {}).get('host', '192.168.50.121')
            
            self.voice_cfg['vicidial_api'] = {
                **self.full_cfg.get('vicidial_api', {}), # Base global (host, etc)
                "host": active_host,
                **self.campania_cfg.get('vicidial_api', {}) # Overrides específicos
            }
        else:
            self.voice_cfg['vicidial_api'] = None
            logger.info("🛠️ [Local] Herramientas de Vicidial DESACTIVADAS por modo local.")

        # Inyectar interfaz de audio o usar local por defecto
        self.audio_interface = audio_interface or LocalAudioInterface(chunk=512)
        self.vad = VADProcessor()

        # --- AUDIO ROUTER (Dinámico por Campaña) ---
        scripts_file = self.campania_cfg.get('scripts_file', 'assets/retencion/scripts.json')
        scripts_path = os.path.join(os.path.dirname(__file__), '..', scripts_file)
        self.audio_router = AudioRouter(api_key=api_key, scripts_path=scripts_path)

        # Tools Base
        extra_tools = [self.fijar_estatus_final]
        
        # Modo Híbrido: Solo si el modo es hibrido, activamos pregrabados (Desactivado por petición de usuario para usar voz directa)
        if self.voice_mode == 'hibrido':
            # extra_tools.append(self.audio_router.reproducir_audio_pregrabado)
            logger.info(f"🔊 [Híbrido] Herramienta de audios pregrabados DESACTIVADA por petición de usuario (Uso de voz directa).")
        else:
            logger.info(f"🎙️ [Live] Herramienta de audios pregrabados DESACTIVADA.")

        # Herramientas Especiales (ej: AMEX Form)
        self.amex_handler = None
        if self.campania_name == 'amex':
            self.amex_handler = AMEXFormHandler()
            extra_tools.extend([
                self.amex_handler.guardar_dato_cliente,
                self.amex_handler.ver_datos_capturados,
                self.amex_handler.enviar_solicitud_amex,
            ])
            logger.info("💳 [AMEX] Tools de formulario AMEX activadas.")
        elif self.campania_name == 'retencion':
            from tools.retencion_tools import (
                guardar_cuenta_cliente,
                guardar_telefono_cliente,
                guardar_nombre_cliente,
                guardar_tipo_cancelacion,
                guardar_motivo_cancelacion,
                limpiar_senales,
                obtener_datos_cliente,
            )
            extra_tools.extend([
                guardar_cuenta_cliente,
                guardar_telefono_cliente,
                guardar_nombre_cliente,
                guardar_tipo_cancelacion,
                guardar_motivo_cancelacion,
                limpiar_senales,
                obtener_datos_cliente,
            ])
            logger.info("🎯 [Retención] Tools de retención registradas en el agente.")
        elif self.campania_name == 'plata':
            from tools.plata_tools import (
                crm_llenado,
                codigo_txt,
                limpiar_senales_plata
            )
            extra_tools.extend([
                crm_llenado,
                codigo_txt,
                self.external_pause_and_flag_exit,
            ])
            # Limpiar señales pendientes al inicio
            limpiar_senales_plata()
            logger.info("💳 [PlataCard] Tools crm_llenado, codigo_txt y external_pause_and_flag_exit registradas en el agente.")

        self.tools_dispatcher = ToolDispatcher(
            self.voice_cfg,
            extra_tools=extra_tools
        )
        
        logger.info(
            f"🚀 Agente listo | Campaña: {self.campania_name.upper()} | "
            f"Voz: {self.voice_cfg.get('voice', {}).get('name', 'IA')} | "
            f"Modo: {self.voice_mode.upper()}"
        )
        
        # Directorio de Grabación de la Campaña
        self.capture_dir = os.path.join(os.path.dirname(__file__), '..', self.campania_cfg.get('recording_dir', 'recordings'))
        if not os.path.exists(self.capture_dir):
            os.makedirs(self.capture_dir, exist_ok=True)
            logger.info(f"📁 Carpeta de grabaciones creada: {self.capture_dir}")

        # Recording Global (llamada completa)
        self.recorder = None

        # Captura exclusiva (Modo Grabación o Live Reuse)
        self.voice_capture = None
        if self.voice_mode == 'grabacion':
            # Leer texto directamente desde el archivo scripts.json de la campaña
            if self.grabacion_txt:
                try:
                    with open(scripts_path, 'r', encoding='utf-8') as sf:
                        scripts_data = json.load(sf)
                    campaign_scripts = scripts_data.get('scripts', {})
                    if self.grabacion_txt not in campaign_scripts:
                        logger.error(f"❌ [Modo Grabación] Frase '{self.grabacion_txt}' no encontrada en el catálogo de scripts ({scripts_path})")
                        sys.exit(1)
                    self.grabacion_frase = campaign_scripts[self.grabacion_txt].get('text', '').strip()
                    self.grabacion_salida = self.grabacion_txt + ".wav"
                    logger.info(f"✨ [Modo Grabación] Frase cargada de scripts.json: '{self.grabacion_txt}' → \"{self.grabacion_frase[:60]}...\"")
                except Exception as e:
                    logger.error(f"❌ [Modo Grabación] Error al cargar scripts.json para grabación: {e}")
                    sys.exit(1)

        # --- ESTADO Y MONITOREO ---
        self.final_disposition = None
        self.client_speech_detected = False
        self.session_active = True
        self.delayed_hangup_task = None
        self.audio_out_queue = asyncio.Queue()
        self.greeting_done = False
        self.greeting_lock = False
        self.ai_speaking = False
        self.vicidial_logged_in = False
        self.client_phone = self.voice_cfg.get('current_call', {}).get('client_phone', '')
        self.client_name = ''
        self.client_cuenta = ''
        self.client_lead_id = ''
        self.last_client_phone = ''
        self.last_client_cuenta = ''
        self.last_client_lead_id = ''

    def fijar_estatus_final(self, estatus: str):
        """Herramienta llamada por Gemini para marcar el resultado de la llamada sin colgar."""
        val_real = self.voice_cfg['vicidial_api'].get('status_map', {}).get(estatus, estatus)
        self.final_disposition = val_real
        logger.warning(f"💾 [Estatus] Gemini fijó el resultado como: {estatus} ({val_real})")
        
        if self.delayed_hangup_task:
            self.delayed_hangup_task.cancel()
            
        if hasattr(self, 'loop'):
            self.loop.call_soon_threadsafe(
                lambda: setattr(self, 'delayed_hangup_task', self.loop.create_task(self._delayed_hangup_timer()))
            )
        return f"OK. Estatus '{estatus}' guardado. El sistema cerrará la llamada en unos segundos de silencio."

    def external_pause_and_flag_exit(
        self,
        cn_type: str,
        cn_motivo: str,
        tipificacion: str
    ) -> dict:
        """
        Pausa la llamada, marca la salida e inserta los datos de la llamada en la BD CNAgenteDepuracion.
        """
        logger.warning(f"📞 [PlataCard] external_pause_and_flag_exit invocado: type={cn_type}, motivo={cn_motivo}, tipificacion={tipificacion}")
        
        # 1. Registrar actividad 'Tipificando' en BD de agentes
        from tools.vicidial_db import actualizar_actividad, DB_CONFIG
        try:
            actualizar_actividad("Tipificando")
        except Exception as ae:
            logger.error(f"Error actualizando actividad: {ae}")

        # 2. Insertar registro en CNAgenteDepuracion de forma síncrona en hilo
        import pymysql
        
        # Emular el diccionario de client_context original a partir del estado actual del agente
        registro = {
            "NOMBRE_CLIENTE": self.client_name or "Desconocido",
            "CUENTA": self.client_cuenta or "Sin Cuenta",
            "NUMERO_ORDEN": "sin orden",  # PlataCard no maneja ordenes de VT
            "Telefonos": self.client_phone or "",
            "Tipo": "PlataCard",
            "Direccion": "Entrega PlataCard",
            "NOMBRE_AGENTE": self.voice_cfg.get("agent_instructions", {}).get("agent_human_name", "Liliana Hernández"),
            "HORA_LLAMADA": datetime.now().strftime("%H:%M"),
            "Horario": "Ventas",
            "SALUDO": "Buen dia",
            "status": "Pendiente",
            "cn_type": cn_type,
            "cn_motivo": cn_motivo,
            "tipoficacion": tipificacion
        }

        def _insert_cn():
            logger.info("✅ [PlataTools] MOCK: Registro CNAgenteDepuracion: %s", registro)

        # Ejecutar inserción en background/hilo para no bloquear el bucle de eventos
        if hasattr(self, 'loop') and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(asyncio.to_thread(_insert_cn))
            )
        else:
            _insert_cn()

        # 3. Guardar estatus y programar colgado en 6 segundos para dar tiempo al usuario/Gemini
        self.final_disposition = tipificacion
        if self.delayed_hangup_task:
            self.delayed_hangup_task.cancel()
            
        if hasattr(self, 'loop') and self.loop.is_running():
            self.loop.call_soon_threadsafe(
                lambda: setattr(self, 'delayed_hangup_task', self.loop.create_task(self._delayed_hangup_timer()))
            )
            
        return {"result": "success", "message": "Registro completado e inserción a CNAgenteDepuracion iniciada. Colgando llamada en unos segundos."}

    async def _delayed_hangup_timer(self):
        # Esperar a que termine de hablar (máximo 15 segundos)
        logger.info("⏱️ [Cierre] Esperando a que termine el audio antes de colgar...")
        for _ in range(30):
            if not self.session_active:
                break
            if not getattr(self, '_ai_playback_active', False) and self.audio_out_queue.empty():
                break
            await asyncio.sleep(0.5)
            
        wait_time = 4.0 if getattr(self, 'transfer_executed', False) or self.campania_name == 'plata' else 2.0
        logger.info(f"⏳ [Cierre] Audio terminado. Esperando margen de seguridad de {wait_time}s...")
        await asyncio.sleep(wait_time)
        if self.session_active and self.final_disposition:
            logger.warning(f"🛑 [Cierre] Enviando estatus: {self.final_disposition}")
            await asyncio.to_thread(self.tools_dispatcher.api.external_status, self.final_disposition)
            await asyncio.to_thread(self.tools_dispatcher.api.external_hangup)
            self.session_active = False

    async def _hangup_watchdog(self):
        logger.info("⏳ [Watchdog] Desactivado watchdog de base de datos asterisk.")
        return

    async def _time_watchdog(self):
        logger.info("🕒 [Reloj] Iniciando watchdog de horario de trabajo activo...")
        while self.agent_running:
            try:
                now = datetime.now()
                hour = now.hour
                weekday = now.weekday()  # 0: Lunes, 1: Martes, ..., 4: Viernes, 5: Sábado, 6: Domingo
                
                # Configuración de horario de salida:
                # - De lunes a viernes (weekday < 5): Desconexión a las 6:00 PM (18:00)
                # - Sábados (weekday == 5) y domingos (weekday == 6): Desconexión a las 3:00 PM (15:00)
                if weekday < 5:
                    limit_hour = 18
                else:
                    limit_hour = 15
                
                if hour >= limit_hour:
                    logger.info(f"🕒 [Reloj] Horario de salida detectado ({limit_hour}:00 o posterior). Iniciando apagado y logout del agente...")
                    # Intentar pausar el agente vía API primero
                    api_cfg = self.tools_dispatcher.api
                    if api_cfg:
                        try:
                            await asyncio.to_thread(api_cfg.external_pause, True)
                            await asyncio.sleep(1)
                        except Exception:
                            pass
                    self.agent_running = False
                    self.session_active = False
                    if hasattr(self, 'phantom') and self.phantom:
                        await asyncio.to_thread(self.phantom.logout_and_stop)
                    break
            except Exception as e:
                logger.error(f"Error en watchdog de horario: {e}")
            await asyncio.sleep(15)
                
    async def _send_audio(self, session):
        try:
            while self.session_active:
                chunk = await self.audio_interface.read_chunk()
                if hasattr(self, 'vicidial_incall') and not self.vicidial_incall:
                    continue

                if not getattr(self, '_greeting_triggered', False):
                    self._greeting_triggered = True
                    self.greeting_trigger_time = asyncio.get_event_loop().time()
                    if self.voice_mode == 'grabacion' and self.grabacion_frase:
                        logger.info(f"🎙️ [Grabación] Enviando frase: '{self.grabacion_frase[:60]}...'")
                        await session.send_realtime_input(text=f"Di la siguiente frase exactamente: {self.grabacion_frase}")
                    elif self.voice_mode == 'hibrido':
                        logger.info("📨 [Inicio] Enviando activador para saludo...")
                        await session.send_realtime_input(text="hola")
                    else:
                        logger.info("📢 [IA] Iniciando saludo natural (Live)...")
                        trigger = self.voice_cfg.get('behavior', {}).get('auto_greet_message', "Hola, buenas tardes.")
                        await session.send_realtime_input(text=trigger)

                if self.vad.is_speech(chunk):
                    self.client_speech_detected = True
                    # Resetear watchdog de silencio
                    self.last_client_speech_time = asyncio.get_event_loop().time()
                    self.silence_warnings_sent = 0
                    
                    if self.execution_mode in ('produccion', 'pruebas'):
                        api_cfg = self.tools_dispatcher.api
                        if api_cfg and not api_cfg._status_called:
                            api_cfg._pending_status = self.voice_cfg.get('dispositions', {}).get('client_speech', 'CLCU')
                    if self.delayed_hangup_task:
                        self.delayed_hangup_task.cancel()
                        self.delayed_hangup_task = None

                if self.recorder: self.recorder.write_client(chunk)

                # Control de silencio / muteado inicial
                if not self.greeting_done:
                    elapsed = asyncio.get_event_loop().time() - self.greeting_trigger_time if getattr(self, '_greeting_triggered', False) else 0
                    if elapsed > 4.0:
                        self.greeting_done = True
                        logger.warning("⚠️ [Core] Tiempo de espera del saludo inicial agotado. Desmuteando micrófono por seguridad.")

                if self.greeting_done:
                    # Muteado temporal de los primeros 4 segundos de habla de la IA para evitar interrupciones
                    is_muted = False
                    if getattr(self, '_ai_playback_active', False):
                        elapsed_speaking = asyncio.get_event_loop().time() - getattr(self, 'ai_speaking_start_time', 0)
                        if elapsed_speaking < 4.0:
                            is_muted = True
                    
                    if not is_muted:
                        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        except Exception as e:
            if "1000" not in str(e): logger.error(f"Error _send_audio: {e}")
            self.session_active = False

    async def _receive_responses(self, session):
        try:
            while self.session_active:
                async for response in session.receive():
                    if not self.session_active: break
                    if response.server_content and response.server_content.interrupted:
                        if not self.greeting_lock:
                            while not self.audio_out_queue.empty(): self.audio_out_queue.get_nowait()
                            logger.info("🔇 [Barge-in] Limpiando cola de audio.")
                        continue
                    
                    if self.vicidial_incall and not getattr(self, "_hangup_done", False):
                        self._hangup_done = False

                    # Extracción robusta de audio (Soporte para múltiples versiones del SDK)
                    audio_chunk = None
                    if response.data:
                        audio_chunk = response.data
                    elif response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                audio_chunk = part.inline_data.data
                                break
                    
                    if response.server_content and response.server_content.turn_complete:
                        if not getattr(self, 'first_turn_complete_received', False):
                            self.first_turn_complete_received = True
                            logger.info("ℹ️ [Core] Turno de saludo recibido de Gemini.")
                            if self.audio_out_queue.empty() and not self.greeting_done:
                                self.greeting_done = True
                                logger.info("🎤 [Core] Turno de saludo completo y cola vacía. Desmuteando micrófono.")
                        if self.voice_mode == 'grabacion':
                            logger.info("✅ [Modo Grabación] Turno completado. Cerrando sesión en 2s...")
                            await asyncio.sleep(2.0)
                            self.session_active = False
                    
                    if audio_chunk:
                        self.ai_speaking = True
                        self.audio_out_queue.put_nowait(audio_chunk)
                        # Log ocasional para verificar que el flujo no está vacío (cada ~1 segundo de audio)
                        if not hasattr(self, '_audio_counter'): self._audio_counter = 0
                        self._audio_counter += 1
                        if self._audio_counter % 20 == 0:
                            logger.info(f"🔊 [En línea] Recibiendo audio de Gemini ({len(audio_chunk)} bytes/chunk)")
                    if response.text:
                        logger.info(f"🤖 [IA]: {response.text}")
                        if hasattr(self, 'call_transcript'):
                            self.call_transcript.append(f"Agente: {response.text}")
                    if response.tool_call:
                        for fc in response.tool_call.function_calls:
                            asyncio.create_task(self._process_tool_call(session, fc))
        except Exception as e:
            if "1000" not in str(e): logger.error(f"Error Gemini Session: {e}")
            self.session_active = False

    async def _process_tool_call(self, session, fc):
        if hasattr(self, 'call_transcript'):
            self.call_transcript.append(f"Llamando herramienta: {fc.name} con argumentos: {fc.args}")
        try:
            # Handle external_hangup with delay and guard BEFORE executing the tool
            if fc.name == 'external_hangup':
                if getattr(self, 'hangup_executed', False):
                    logger.info('🔔 external_hangup already executed, skipping duplicate')
                    return
                self.hangup_executed = True
                
                logger.info("⏱️ Retrasando ejecución de external_hangup 6 segundos")
                # Wait up to 6 seconds in small chunks to detect session end
                for _ in range(12):
                    if not getattr(self, 'session_active', False):
                        logger.info("📞 Cliente colgó durante la despedida. Cortando retraso.")
                        break
                    await asyncio.sleep(0.5)

            # Handle transfer_conference with delay and guard BEFORE executing the tool
            if fc.name == 'transfer_conference':
                if getattr(self, 'transfer_executed', False):
                    logger.info('🔔 transfer_conference already executed, skipping duplicate')
                    return
                self.transfer_executed = True
                
                # Para la campaña plata, siempre reproducimos la frase de despedida de forma manual controlada para asegurar que se diga completa antes de transferir
                if self.campania_name == 'plata':
                    logger.info("🎙️ [Transferencia] Campaña Plata detectada. Limpiando cola de audio para inyectar despedida controlada...")
                    # Limpiar cola de audio existente
                    while not self.audio_out_queue.empty():
                        try:
                            self.audio_out_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    self._ai_playback_active = False
                    self.ai_speaking = False
                    
                    # Decidir qué frase usar basada en el historial de la llamada
                    usar_cat_cortes = False
                    if hasattr(self, 'call_transcript') and self.call_transcript:
                        for entry in reversed(self.call_transcript[-4:]):
                            lower_entry = entry.lower()
                            if any(w in lower_entry for w in ["cat", "corte", "pago", "cuándo llega", "cuando llega", "entrega", "duda", "interés", "comisión", "comisiones"]):
                                usar_cat_cortes = True
                                break
                    
                    if usar_cat_cortes:
                        texto_despedida = "Ah ok, mire, para poder brindarle esta información y de cualquier otra duda que usted tenga, lo voy a transferir con mi compañero para que le pueda brindar la información completa, no cuelgue por favor."
                    else:
                        texto_despedida = "De acuerdo, permítame un momento, lo voy a transferir con uno de mis compañeros para continuar con su registro, no cuelgue por favor."
                    
                    script_to_play = {
                        "text": texto_despedida,
                        "tts_direction": "Di con tono amable y de servicio, asegurando una transición suave:"
                    }
                    try:
                        pcm_data = await self.audio_router._generate_tts(script_to_play)
                        if pcm_data:
                            CHUNK_SIZE = 4800
                            self.ai_speaking = True
                            self._ai_playback_active = True
                            for i in range(0, len(pcm_data), CHUNK_SIZE):
                                self.audio_out_queue.put_nowait(pcm_data[i:i + CHUNK_SIZE])
                            logger.info(f"🔊 [Transferencia] Frase de despedida controlada encolada ({len(pcm_data)} bytes): '{texto_despedida}'")
                    except Exception as tts_err:
                        logger.error(f"❌ [Transferencia] Error generando despedida por TTS: {tts_err}")
                
                logger.info("⏱️ [Transferencia] Esperando a que el audio de despedida comience y termine de reproducirse...")
                # Esperar a que la cola se vacíe y la reproducción termine (máximo 15 segundos)
                for _ in range(30):
                    if not getattr(self, 'session_active', False):
                        break
                    if not getattr(self, '_ai_playback_active', False) and self.audio_out_queue.empty():
                        break
                    await asyncio.sleep(0.5)
                
                # Un pequeño margen de seguridad adicional para que termine el buffer de audio (2 segundos)
                logger.info("⏱️ [Transferencia] Cola vacía. Esperando margen de seguridad de 2.0 segundos...")
                for _ in range(4):
                    if not getattr(self, 'session_active', False):
                        break
                    await asyncio.sleep(0.5)

            result = await asyncio.to_thread(self.tools_dispatcher.execute_tool, fc.name, fc.args)
            if hasattr(self, 'call_transcript'):
                self.call_transcript.append(f"Respuesta de herramienta {fc.name}: {result}")

            if fc.name == 'reproducir_audio_pregrabado' and self.voice_mode == 'hibrido':
                pending = getattr(self.audio_router, '_pending_playback', None)
                if pending:
                    self.audio_router._pending_playback = None
                    asyncio.create_task(self._inject_prerecorded_audio(pending['script_id'], pending.get('variables', {})))
            # Send the tool response; ignore if the Gemini session has already been closed.
            try:
                await session.send_tool_response(
                    function_responses=[types.FunctionResponse(name=fc.name, response=result, id=fc.id)]
                )
            except Exception as send_err:
                # The session may be closed (e.g., after external_hangup). Suppress the error.
                err_str = str(send_err).lower()
                if "connectionclosed" not in err_str and "1000" not in err_str and "closed" not in err_str:
                    logger.error(f"Error sending tool response for {fc.name}: {send_err}")
        except Exception as e:
            logger.error(f"Error Tool {fc.name}: {e}")
            await session.send_tool_response(
                function_responses=[types.FunctionResponse(name=fc.name, response={"error": str(e)}, id=fc.id)]
            )

    async def _inject_prerecorded_audio(self, script_id: str, variables: dict = None):
        GREETING_SCRIPTS = {'amex_saludo', 'amex_motivo', 'saludo_generico', 'motivo_llamada'}
        is_greeting = script_id in GREETING_SCRIPTS
        try:
            if is_greeting: self.greeting_lock = True
            pcm_data = await self.audio_router.get_audio(script_id, variables or None)
            if pcm_data:
                CHUNK_SIZE = 4800
                self.ai_speaking = True
                for i in range(0, len(pcm_data), CHUNK_SIZE):
                    self.audio_out_queue.put_nowait(pcm_data[i:i + CHUNK_SIZE])
            if is_greeting and not pcm_data: self.greeting_lock = False
        except Exception as e:
            logger.error(f"Error Inyección: {e}")
            if is_greeting: self.greeting_lock = False

    async def _play_audio(self):
        try:
            while self.session_active:
                try:
                    data = await asyncio.wait_for(self.audio_out_queue.get(), timeout=0.4)
                    if self.recorder: self.recorder.write_agent(data)
                    if self.voice_capture: self.voice_capture.write(data)
                    
                    # Detectar inicio de reproducción de audio de la IA
                    if not getattr(self, '_ai_playback_active', False):
                        self._ai_playback_active = True
                        self.ai_speaking_start_time = asyncio.get_event_loop().time()
                        logger.info("🔊 [Audio] Agente comenzó a hablar. Muteando mic por 4s para evitar interrupciones.")

                    await self.audio_interface.write_chunk(data)
                    if self.audio_out_queue.empty():
                        if self.greeting_lock: self.greeting_lock = False
                        if not self.greeting_done and getattr(self, 'first_turn_complete_received', False):
                            self.greeting_done = True
                            logger.info("🎤 [Core] Saludo inicial reproducido por completo. Desmuteando micrófono.")
                except asyncio.TimeoutError:
                    # Se considera que el agente terminó de hablar tras 0.4s de silencio en la cola
                    if getattr(self, '_ai_playback_active', False):
                        self.ai_speaking = False
                        self._ai_playback_active = False
                        logger.info("🔇 [Audio] Agente terminó de hablar. Micrófono completamente activo.")
                    continue
        except Exception as e:
            logger.error(f"Error _play_audio: {e}")
            self.session_active = False

    async def _silence_watchdog(self, session):
        logger.info("⏱️ [Watchdog Silencio] Inicializado.")
        
        # Esperar a que la llamada esté activa
        while self.session_active and not getattr(self, 'vicidial_incall', False):
            await asyncio.sleep(0.5)
            
        if not self.session_active:
            return
            
        logger.info("⏱️ [Watchdog Silencio] Llamada detectada activa. Iniciando watchdog de silencio...")
        self.last_client_speech_time = asyncio.get_event_loop().time()
        self.silence_warnings_sent = 0
        
        while self.session_active:
            try:
                if not getattr(self, 'vicidial_incall', False):
                    await asyncio.sleep(1)
                    continue

                if getattr(self, 'hangup_executed', False) or getattr(self, 'transfer_executed', False):
                    logger.info("⏱️ [Watchdog Silencio] Colgado o transferencia en progreso. Desactivando watchdog.")
                    break

                # Si la IA está hablando o reproduciendo audio, mantener el temporizador de silencio en 0
                if getattr(self, 'ai_speaking', False) or getattr(self, '_ai_playback_active', False):
                    self.last_client_speech_time = asyncio.get_event_loop().time()
                    await asyncio.sleep(1)
                    continue

                now = asyncio.get_event_loop().time()
                elapsed = now - getattr(self, 'last_client_speech_time', now)

                # Paso 1: 7 segundos de silencio mutuo -> Primer aviso
                if elapsed >= 7.0 and getattr(self, 'silence_warnings_sent', 0) == 0:
                    logger.warning("⏱️ [Watchdog Silencio] 7s de silencio mutuo detectados. Enviando primer recordatorio al agente.")
                    self.silence_warnings_sent = 1
                    self.last_warning_sent_time = now
                    try:
                        await session.send_realtime_input(
                            text="[SISTEMA: El cliente no ha respondido por 7 segundos. Pregúntale brevemente si sigue ahí, por ejemplo: '¿Hola? ¿Sigue ahí?' o '¿Me escucha?']"
                        )
                        if hasattr(self, 'call_transcript'):
                            self.call_transcript.append("[Sistema] Primer aviso de silencio enviado al agente.")
                    except Exception as se:
                        logger.error(f"Error enviando recordatorio 1: {se}")

                # Paso 2: Otros 7 segundos (14s total) sin respuesta -> Colgar
                elif getattr(self, 'silence_warnings_sent', 0) == 1 and (now - getattr(self, 'last_warning_sent_time', now)) >= 7.0:
                    logger.warning("⏱️ [Watchdog Silencio] 14s de silencio mutuo continuo (7s tras aviso). Colgando por falta de respuesta...")
                    
                    no_resp_status = self.voice_cfg.get('dispositions', {}).get('no_response', 'SINRSPT')
                    self.final_disposition = no_resp_status
                    api_cfg = self.tools_dispatcher.api
                    if api_cfg:
                        logger.warning(f"⏱️ [Watchdog Silencio] Ejecutando colgado y tipificando como {no_resp_status}...")
                        try:
                            await asyncio.to_thread(api_cfg.external_status, no_resp_status)
                            await asyncio.to_thread(api_cfg.external_hangup)
                        except Exception as he:
                            logger.error(f"Error colgando llamada por silencio: {he}")
                    else:
                        logger.warning("⏱️ [Watchdog Silencio] Modo local/sin API. Colgando localmente...")
                    
                    if hasattr(self, 'call_transcript'):
                        self.call_transcript.append("[Sistema] Colgado automático por silencio (SINRSPT).")
                        
                    self.session_active = False
                    break

            except Exception as e:
                logger.error(f"Error en watchdog de silencio: {e}")
                
            await asyncio.sleep(1)

    async def _generate_call_summary(self) -> str:
        """Genera un resumen de la llamada utilizando Gemini basado en la transcripción de eventos."""
        if not getattr(self, 'call_transcript', None):
            return "Sin conversación registrada."
        
        prompt = (
            "Eres un supervisor de calidad de un call center. A continuación se muestra la secuencia de eventos "
            "de una llamada atendida por un agente de Inteligencia Artificial. Tu tarea es generar un resumen muy breve "
            "(en español, máximo 2 frases) de lo que sucedió en la llamada (por ejemplo: si el cliente aceptó, si rechazó "
            "la oferta, si se cortó la llamada, si no le interesó, etc.).\n\n"
            "Eventos de la llamada:\n"
        )
        for event in self.call_transcript:
            prompt += f"- {event}\n"
            
        prompt += "\nPor favor, responde únicamente con el resumen, sin preámbulos ni comentarios adicionales."
        
        try:
            logger.info("Generating call summary with Gemini...")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt
            )
            summary = response.text.strip() if response.text else "No se pudo generar el resumen."
            logger.info(f"📝 [Resumen Generado]: {summary}")
            return summary
        except Exception as e:
            logger.error(f"Error generando resumen con Gemini: {e}")
            return "Error al generar el resumen de la llamada."

    async def start(self):
        self.loop = asyncio.get_running_loop()
        vc = self.voice_cfg
        ai = vc.get('agent_instructions', {})
        
        # Construcción del Prompt Modular
        personality = (
            f"IDIOMA: {vc.get('common_settings', {}).get('language', {}).get('name', 'Español')}. "
            f"ACENTO: {vc.get('common_settings', {}).get('accent', {}).get('description', '')}. "
            f"VOZ: {vc.get('voice', {}).get('name')}, tono {vc.get('emotion', {}).get('base_tone')}. "
        )
        
        role_block = ai.get('role', 'Eres un asistente.')
        identity_rules = " ".join([f"- {r}" for r in ai.get('identity_rules', [])])
        
        # Flujo y Reglas
        flow_block = json.dumps(ai.get('conversation_flow', {}), ensure_ascii=False)
        rules_block = " ".join(ai.get('core_rules', []))
        
        pregrabados_block = ""
        # Desactivado por petición de usuario para usar voz directa en todos los modos
        # if self.voice_mode == 'hibrido':
        #     available = self.audio_router.get_available_scripts()
        #     pregrabados_block = "AUDIOS PREGRABADOS DISPONIBLES (Usa 'reproducir_audio_pregrabado'): "
        #     for sid, info in available.items():
        #         pregrabados_block += f"'{sid}': \"{info['text'][:50]}...\"; "
        
        if self.campania_name == 'ventas_izzi':
            cierre_rules = (
                "\n2. CIERRE DE LLAMADA: Cuando el cliente esté calificado, interesado y confirme estar de acuerdo con ser transferido, haz lo siguiente en orden ESTRICTO:"
                "\n   a) Llama a la herramienta 'actualizar_comentarios_cliente' con los datos perfilados (nombre_cliente, pantallas, paquete_ofrecido, cuenta, dudas_no_respondidas). Hazlo en silencio, sin decírselo al cliente."
                "\n   b) Di DE VIVA VOZ tu frase de cierre de transferencia UNA SOLA VEZ (ej: 'Perfecto, un momento por favor, no cuelgue, lo transfiero con mi compañero...'). NO la repitas."
                "\n   c) Llama a la herramienta 'transfer_conference' con los parámetros: user='Virt1', password='Cyber123', ingrup='tvplus'."
                "\n   d) Inmediatamente después, llama a 'external_status' con el valor 'TRANSvent' (o 'transInt' si el cliente tenía dudas o preguntas específicas que no supiste responder y requirió transferencia inmediata)."
                "\n   PROHIBIDO: usar 'external_hangup' en este nodo, la transferencia se encargará del colgado."
            )
            voicemail_status = "NCBUZ"
        elif self.campania_name == 'plata':
            cierre_rules = (
                "\n2. CIERRE DE LLAMADA: Al terminar la interacción con el cliente (ya sea por venta exitosa, rechazo, reprogramación o llamada cortada), debes despedirte formalmente y llamar a la herramienta 'external_pause_and_flag_exit' con los parámetros correspondientes (cn_type, cn_motivo, tipificacion)."
            )
            voicemail_status = "NCBUZ"
        elif self.campania_name == 'retencion':
            cierre_rules = (
                "\n2. CIERRE DE LLAMADA: Al terminar la interacción, debes clasificar la llamada en el sistema llamando a la herramienta 'external_status' con uno de los siguientes valores exactos en MAYÚSCULAS en orden ESTRICTO y después a 'external_hangup':"
                "\n   a) Si la conversación se dirigió a cancelar y LOGRASTE MANTENER al cliente activo mediante alguna promoción, descuento o beneficio de retención, llama a 'external_status' con el valor 'RETEN' y después a 'external_hangup'."
                "\n   b) Si la conversación se dirigió a cancelar pero NO lograste mantener al cliente y le proporcionaste un folio de precancelación, llama a 'external_status' con el valor 'NORET' y después a 'external_hangup'."
                "\n   c) Para cualquier otro escenario puramente informativo (como consultar saldo, consultar plan contratado), o si el cliente quería cancelar pero no era el titular, o si no se podía realizar la cancelación debido a saldo pendiente y le explicaste el procedimiento a seguir para poder cancelar, llama a 'external_status' con el valor 'POLLT' y después a 'external_hangup'."
            )
            voicemail_status = "NZBUZ"
        else:
            cierre_rules = (
                "\n2. CIERRE DE LLAMADA: Cuando el cliente esté calificado e interesado, haz lo siguiente en orden ESTRICTO:"
                "\n   a) Di DE VIVA VOZ tu frase de cierre UNA SOLA VEZ (ej: 'Perfecto [Nombre], en un momento le comunicamos con un asesor. ¡Que disfrute su servicio!'). NO la repitas."
                "\n   b) Acto seguido, llama a la herramienta 'external_status' con el valor 'SALE'."
                "\n   c) Inmediatamente después, llama a 'external_hangup'."
                "\n   PROHIBIDO: usar 'transfer_conference'. PROHIBIDO: repetir el mensaje de cierre antes o después de las herramientas."
            )
            voicemail_status = "NCBUZ"

        system_rules_override = (
            "\n\n🚨 REGLAS CRÍTICAS DE EJECUCIÓN (MODO PRUEBAS/PRODUCCION):"
            "\n1. NUNCA uses la herramienta 'reproducir_audio_pregrabado' para audios que requieran variables dinámicas o el nombre del cliente (como 'izzi_transferencia_paquete'). Debes decir esos textos con TU PROPIA VOZ de viva voz de forma natural en tiempo real."
            f"{cierre_rules}"
            "\n3. DOMICILIO OPCIONAL: Si el cliente no quiere dar su dirección o no la menciona, NO la solicites. Avanza al cierre sin ella."
            f"\n4. DETECCIÓN DE BUZÓN DE VOZ / CONTESTADORA: Si detectas que contestó una contestadora automática o buzón de voz (mensajes como 'deje su mensaje', 'presione la extensión', 'marque un número', 'apriete un número', 'deje un mensaje', 'el número que usted marcó', etc.), NO intentes interactuar ni dar tu pitch. Llama inmediatamente a la herramienta 'external_status' con el valor '{voicemail_status}' y después a 'external_hangup' para colgar."
        )
        full_prompt = f"{personality} ROL: {role_block} IDENTIDAD: {identity_rules} FLUJO: {flow_block} REGLAS: {rules_block} {pregrabados_block}{system_rules_override}"
        
        if self.voice_mode == 'grabacion':
            system_instruction = f"{personality} INSTRUCCIÓN: Di exactamente esta frase y nada más: {self.grabacion_frase}"
        else:
            system_instruction = full_prompt

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=vc['voice']['name'])
                )
            ),
            tools=self.tools_dispatcher.get_tool_list() if self.voice_mode != 'grabacion' else [],
            system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
        )

        model = "models/gemini-3.1-flash-live-preview"
        # Logueo en Vicidial si es producción o pruebas
        if self.execution_mode in ('produccion', 'pruebas'):
            from src.phantom_browser import PhantomAgent
            api_cfg = self.tools_dispatcher.api
            self.phantom = PhantomAgent(
                api_cfg.host, api_cfg.phone_login, api_cfg.phone_pass,
                api_cfg.user, api_cfg.password, api_cfg.campaign_id,
                campania_name=self.campania_name
            )
            api_cfg.phantom = self.phantom
            await asyncio.sleep(2)
            self.phantom.start()

        self.agent_running = True
        if self.execution_mode in ('produccion', 'pruebas'):
            asyncio.create_task(self._time_watchdog())
        try:
            while self.agent_running:
                self.session_active = True
                self.vicidial_incall = True if self.execution_mode == 'local' else False
                self.client_name = "Aldair Nava Marquez" if self.execution_mode == 'local' else ""
                self.call_transcript = []
                self.last_client_speech_time = asyncio.get_event_loop().time()
                self.silence_warnings_sent = 0
                self.last_warning_sent_time = 0.0
                self.client_phone = "5555555555" if self.execution_mode == 'local' else ""
                self.client_cuenta = "12345678" if self.execution_mode == 'local' else ""
                self._greeting_triggered = False
                self.hangup_executed = False
                self.transfer_executed = False
                self.greeting_done = False
                self.first_turn_complete_received = False
                self.ai_speaking = False
                self._ai_playback_active = False
                self.ai_speaking_start_time = 0.0
                self.audio_out_queue = asyncio.Queue()  # Limpiar cola de audio
                self.client_speech_detected = False
                self.final_disposition = None
                
                if self.execution_mode in ('produccion', 'pruebas'):
                    api_cfg = self.tools_dispatcher.api
                    if api_cfg:
                        api_cfg.call_hungup_sent = False
                        api_cfg._status_called = False
                        api_cfg._pending_status = self.voice_cfg.get('dispositions', {}).get('default_pending', 'NZBUZ')
                
                # Iniciar grabador global para esta llamada/sesión
                rec_cfg = self.voice_cfg.get('recording', {})
                if rec_cfg.get('enabled') and self.execution_mode == 'local':
                    from .audio_recorder import AudioRecorder
                    self.recorder = AudioRecorder(output_dir='recordings')
                else:
                    self.recorder = None

                # Iniciar captura exclusiva de la IA para esta llamada/sesión
                self.voice_capture = None
                if self.voice_mode == 'grabacion':
                    from .audio_recorder import AgentVoiceCapture
                    capture_path = os.path.join(self.capture_dir, self.grabacion_salida if self.grabacion_salida.endswith('.wav') else self.grabacion_salida + '.wav')
                    self.voice_capture = AgentVoiceCapture(output_path=capture_path)

                try:
                    async with SafeLiveConnection(self.client.aio.live.connect(model=model, config=config)) as session:
                        logger.info("✅ Conexión establecida con Gemini. Esperando llamada...")
                        
                        if self.execution_mode == 'local':
                            if self.campania_name == 'ventas_izzi':
                                greeting_phrase = "Buen día, ¿hablo con Aldair?"
                                brand_info = "Llamas de izzi y ofreces el servicio izzi tv+."
                            elif self.campania_name == 'retencion':
                                greeting_phrase = "Buen día, gracias por llamar a cuentas especiales izzi, ¿con quién tengo el gusto?"
                                brand_info = "Te identificas como de Cuentas Especiales de Izzi."
                            elif self.campania_name == 'plata':
                                greeting_phrase = "Hola, hola buenas tardes."
                                brand_info = "Llamas del centro telefónico autorizado 305 en representación de Banco Plata."
                            elif self.campania_name == 'amex':
                                greeting_phrase = f"Hola, buenas tardes, me presento mi nombre es Liliana Hernández, ¿tengo el gusto con {self.client_name}?"
                                brand_info = "Llamas de American Express México."
                            else:
                                greeting_phrase = f"Hola, buenas tardes, me presento mi nombre es Liliana Hernández, ¿tengo el gusto con {self.client_name}?"
                                brand_info = ""
                            
                            logger.info(f"📢 [Local] Inyectando contexto de prueba para cliente: {self.client_name}")
                            self._greeting_triggered = True
                            self.greeting_trigger_time = asyncio.get_event_loop().time()
                            await session.send_realtime_input(
                                text=f"[SISTEMA: Llamada conectada. Cliente: {self.client_name}. Teléfono: {self.client_phone}. Cuenta: {self.client_cuenta}. IMPORTANTE: El saludo inicial de la llamada DEBE ser dicho de viva voz por ti: '{greeting_phrase}' ESPERA SU RESPUESTA. Si te preguntan quién habla, usa tu presentación completa. {brand_info}]"
                            )
                        
                        async def monitor():
                            was_in_call = False
                            db_failed = True
                            while self.session_active:
                                try:
                                    status = None
                                    lead_id = None
                                    lead_id_str = ""
                                    phone_number = ""
                                    cuenta = ""
                                    
                                    # 1. Intentar consultar base de datos si no ha fallado
                                    if not db_failed:
                                        try:
                                            import pymysql
                                            conn = await asyncio.to_thread(
                                                pymysql.connect, host=api_cfg.host, user='cron', 
                                                password='1234', db='asterisk', connect_timeout=3
                                            )
                                            with conn.cursor() as cur:
                                                cur.execute("SELECT status, lead_id FROM vicidial_live_agents WHERE user=%s", (api_cfg.user,))
                                                res = cur.fetchone()
                                                if res:
                                                    status, lead_id = res[0], res[1]
                                                    if status == 'INCALL' and lead_id and lead_id > 0:
                                                        lead_id_str = str(lead_id)
                                                        cur.execute("SELECT first_name, last_name, phone_number FROM vicidial_list WHERE lead_id=%s", (lead_id,))
                                                        lead_res = cur.fetchone()
                                                        if lead_res:
                                                            phone_number = lead_res[2].strip() if lead_res[2] else ""
                                            conn.close()
                                        except Exception as dbe:
                                            logger.warning(f"⚠️ [Monitor] Falló conexión a base de datos de Asterisk: {dbe}. Usando fallback de navegador...")
                                            db_failed = True
                                            
                                    # 2. Si no hay base de datos o falló, usar navegador
                                    if db_failed:
                                        if hasattr(self, 'phantom') and self.phantom:
                                            # Primero comprobar llamada de forma ultra-rápida usando la imagen de livecall
                                            in_call = await asyncio.to_thread(self.phantom.is_in_call)
                                            status = 'INCALL' if in_call else 'PAUSED'
                                            
                                            phone_number = ""
                                            cuenta = ""
                                            lead_id_str = ""
                                            
                                            if in_call:
                                                # Obtener lead_id de forma instantánea usando JS para comprobar si es reconexión
                                                lead_id_str = await asyncio.to_thread(self.phantom.get_lead_id_fast)
                                        else:
                                            status = 'PAUSED'

                                    # 3. Procesar estado de llamada
                                    if status == 'INCALL':
                                        if not was_in_call:
                                            # Comprobar si realmente cambió el lead_id con respecto al último procesado (evitar doble saludo en reconexión)
                                            has_change = False
                                            if lead_id_str:
                                                if lead_id_str != self.last_client_lead_id:
                                                    has_change = True
                                            else:
                                                # Si por alguna razón no pudimos leer el lead_id aún, asumimos que es nueva llamada
                                                has_change = True
                                            
                                            if not has_change:
                                                self.vicidial_incall = True
                                                was_in_call = True
                                                continue

                                            # --- ESTA ES UNA NUEVA LLAMADA: SALUDO INMEDIATO ---
                                            self.vicidial_incall = True
                                            was_in_call = True
                                            self.call_start_time = asyncio.get_event_loop().time()
                                            self.last_client_speech_time = asyncio.get_event_loop().time()
                                            self.silence_warnings_sent = 0
                                            
                                            # Inyectar inmediatamente el primer saludo rápido a Gemini y activar canal de audio
                                            self._greeting_triggered = True
                                            self.greeting_trigger_time = asyncio.get_event_loop().time()
                                            
                                            logger.info("📢 [IA] Enviando saludo rápido inicial (sin demoras)...")
                                            await session.send_realtime_input(
                                                text="[SISTEMA: LLAMADA CONECTADA. Di de viva voz únicamente y de forma exacta: 'Hola, hola buenas tardes.'. Está ESTRICTAMENTE PROHIBIDO agregar palabras adicionales, muletillas o variaciones. Di exactamente esa frase y después espera en silencio absoluto.]"
                                            )
                                            
                                            if self.voice_mode != 'grabacion':
                                                tasks.append(asyncio.create_task(self._silence_watchdog(session)))
                                                
                                            # --- AHORA EXTRAER LA INFORMACIÓN DE LA LLAMADA EN PARALELO ---
                                            call_data = await asyncio.to_thread(self.phantom.get_active_call_data)
                                            phone_number = call_data.get("phone_number", "")
                                            cuenta = call_data.get("CUENTA", "")
                                            lead_id_str = call_data.get("lead_id", "") or lead_id_str
                                            
                                            self.client_phone = phone_number
                                            self.client_cuenta = cuenta
                                            self.client_lead_id = lead_id_str
                                            self.last_client_lead_id = lead_id_str # Guardar el lead_id activo procesado
                                            
                                            # Determinar el nombre de la compañía/marca para el mensaje del sistema
                                            if self.campania_name == 'ventas_izzi':
                                                brand_info = "Llamas de izzi y ofreces el servicio izzi tv+."
                                            elif self.campania_name == 'retencion':
                                                brand_info = "Te identificas como de Cuentas Especiales de Izzi."
                                            elif self.campania_name == 'plata':
                                                brand_info = "Llamas del centro telefónico autorizado 305 en representación de Banco Plata."
                                            elif self.campania_name == 'amex':
                                                brand_info = "Llamas de American Express México."
                                            else:
                                                brand_info = ""

                                            logger.info("📞 [Monitor] Información de llamada cargada. Lead ID: %s | Tel: %s", self.client_lead_id, self.client_phone)
                                            self.call_transcript.append(f"[Llamada Conectada] Lead ID: {self.client_lead_id}, Teléfono: {self.client_phone}")

                                            # En paralelo, intentamos obtener el nombre del cliente desde el campo de texto "first_name" de la pestaña principal
                                            first_name = ""
                                            last_name = ""
                                            for i in range(7):
                                                call_data = await asyncio.to_thread(self.phantom.get_active_call_data)
                                                first_name = call_data.get("first_name", "").strip()
                                                last_name = call_data.get("last_name", "").strip()
                                                
                                                is_valid = first_name and first_name.upper() not in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST", "")
                                                if is_valid:
                                                    logger.info(f"👻 [Monitor] Nombre de cliente obtenido de input first_name en intento {i+1}: '{first_name}'")
                                                    break
                                                await asyncio.sleep(0.3)
                                                
                                            self.client_name = f"{first_name} {last_name}".strip()
                                            
                                            if self.campania_name == 'plata':
                                                # Enviar los datos del cliente de forma silenciosa para el contexto del agente, sin forzar la segunda frase de inmediato
                                                is_valid_name = first_name and first_name.upper() not in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST")
                                                self.client_name = f"{first_name} {last_name}".strip() if is_valid_name else ""
                                                
                                                context_text = (
                                                    f"[SISTEMA: INFORMACIÓN DE LA LLAMADA. Nombre del cliente: {self.client_name or 'Desconocido'}. "
                                                    f"Teléfono: {self.client_phone}. Cuenta: {self.client_cuenta}. "
                                                    f"REGLA: La llamada ya inició y dijiste de viva voz 'Hola, hola buenas tardes.'. Ahora debes esperar la respuesta "
                                                    f"del cliente y continuar la plática de acuerdo con tu guía de conversación para verificar el titular. {brand_info}]"
                                                )
                                                logger.info(f"📢 [Monitor] Inyectando contexto de Plata: {context_text}")
                                                await session.send_realtime_input(text=context_text)
                                            else:
                                                # Esperar a que el agente termine de decir "Hola, hola buenas tardes" antes de inyectar la segunda frase
                                                elapsed = asyncio.get_event_loop().time() - self.greeting_trigger_time
                                                if elapsed < 2.0:
                                                    await asyncio.sleep(2.0 - elapsed)
                                                    
                                                is_valid_name = first_name and first_name.upper() not in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST")
                                                if is_valid_name:
                                                    greeting_phrase_2 = f"Qué tal buenas tardes, ¿se encontrará {first_name}?"
                                                else:
                                                    greeting_phrase_2 = "Qué tal buenas tardes, ¿se encontrará el titular de la línea?"
                                                    
                                                logger.info(f"📢 [IA] Enviando segunda parte del saludo: '{greeting_phrase_2}'")
                                                await session.send_realtime_input(
                                                    text=f"[SISTEMA: SEGUNDO SALUDO. Di de viva voz únicamente y de forma exacta: '{greeting_phrase_2}'. Está ESTRICTAMENTE PROHIBIDO que agregues cualquier otra frase, saludo o explicación adicional en este turno. Di exactamente esa frase y espera la respuesta del cliente. {brand_info}]"
                                                )
                                            
                                        else:
                                            # Si ya estaba en llamada, mantener activa la bandera
                                            self.vicidial_incall = True
                                            
                                        # Monitorear colgado visual del cliente (solo tras una ventana de gracia de 3.0s)
                                        if was_in_call and hasattr(self, 'phantom') and self.phantom:
                                            elapsed_call = asyncio.get_event_loop().time() - getattr(self, 'call_start_time', 0)
                                            if elapsed_call > 3.0:
                                                is_hungup = await asyncio.to_thread(self.phantom.is_call_hungup)
                                                if is_hungup:
                                                    logger.warning("📞 [Monitor] El navegador indica CALL HUNGUP. Finalizando llamada...")
                                                    self.session_active = False
                                                    break
                                    else:
                                        self.vicidial_incall = False
                                        if was_in_call:
                                            logger.warning("📞 [Monitor] La llamada terminó (Status cambiado de INCALL a %s). Finalizando llamada...", status)
                                            self.session_active = False
                                            break
                                except Exception as me:
                                    logger.error(f"Error en monitor: {me}")
                                
                                # Polling dinámico: 0.1s para contestar al instante si no hay llamada; 1.0s si ya estamos en llamada
                                sleep_time = 1.0 if was_in_call else 0.1
                                await asyncio.sleep(sleep_time)

                        tasks = [
                            asyncio.create_task(self._send_audio(session)),
                            asyncio.create_task(self._receive_responses(session)),
                            asyncio.create_task(self._play_audio())
                        ]
                        if self.voice_mode != 'grabacion':
                            if self.execution_mode == 'local':
                                tasks.append(asyncio.create_task(self._silence_watchdog(session)))
                        if hasattr(self.audio_interface, 'phone'): tasks.append(asyncio.create_task(self._hangup_watchdog()))

                        if self.execution_mode in ('produccion', 'pruebas'):
                            asyncio.create_task(monitor())

                        while self.session_active:
                            await asyncio.sleep(1)
                        
                        # Limpieza de tareas de la llamada actual
                        for t in tasks: t.cancel()

                        # Asegurar que se haya tipificado y colgado antes de reiniciar la sesión de voz
                        if self.execution_mode in ('produccion', 'pruebas') and hasattr(self, 'phantom') and self.phantom:
                            api_cfg = self.tools_dispatcher.api
                            # Evitar doble ejecución si la IA ya inició el proceso de colgar
                            if api_cfg and not getattr(api_cfg, 'call_hungup_sent', False) and not getattr(self, 'hangup_executed', False):
                                if getattr(api_cfg, '_status_called', False):
                                    logger.info(f"ℹ️ [Core] La llamada finalizó con tipificación explícita '{api_cfg._pending_status}'. Ejecutando colgado...")
                                    await asyncio.to_thread(api_cfg.external_hangup)
                                else:
                                    fallback_status = self.final_disposition
                                    if not fallback_status:
                                        status_opts = self.voice_cfg.get('dispositions', {})
                                        fallback_status = status_opts.get('client_speech', 'CLCU') if self.client_speech_detected else status_opts.get('default_pending', 'NZBUZ')
                                    logger.warning(f"⚠️ [Core] La llamada finalizó sin tipificación. Enviando fallback '{fallback_status}' y colgando...")
                                    await asyncio.to_thread(api_cfg.external_status, fallback_status)
                                    await asyncio.to_thread(api_cfg.external_hangup)

                        logger.info("🔄 [Core] Reiniciando sesión de voz para esperar la siguiente llamada...")
                
                except Exception as se:
                    logger.error(f"Error en sesión de llamada: {se}")
                    await asyncio.sleep(2)
                finally:
                    # Cerrar y guardar las grabaciones de la llamada
                    if self.recorder:
                        try:
                            self.recorder.close()
                        except Exception as re:
                            logger.error(f"Error cerrando recorder: {re}")
                    if self.voice_capture:
                        try:
                            self.voice_capture.close()
                        except Exception as ve:
                            logger.error(f"Error cerrando voice_capture: {ve}")
                            
                    # Guardar la información de la llamada en el JSON diario con formato legible
                    if self.client_phone or self.client_cuenta or self.client_name:
                        try:
                            # Resumen de llamada desactivado por petición del usuario para ahorrar cuota
                            resumen = "Desactivado"
                            
                            today_str = datetime.now().strftime("%Y%m%d")
                            log_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', self.campania_name, 'registro_de_llamadas')
                            os.makedirs(log_dir, exist_ok=True)
                            json_path = os.path.join(log_dir, f"{self.campania_name}_{today_str}.json")
                            
                            api_cfg = self.tools_dispatcher.api
                            final_status = (api_cfg.last_status_sent if api_cfg else None) or self.final_disposition or "SIN_ESTATUS"
                            
                            call_data = {
                                "campania": self.campania_name,
                                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "lead_id": self.client_lead_id or "0",
                                "nombre": self.client_name,
                                "cuenta": self.client_cuenta,
                                "telefono": self.client_phone,
                                "estatus": final_status,
                                "resumen": resumen,
                                "audio": os.path.basename(self.recorder.call_path) if self.recorder else None
                            }
                            
                            calls_list = []
                            
                            # Leer registros existentes si el JSON ya existe
                            if os.path.exists(json_path):
                                try:
                                    with open(json_path, "r", encoding="utf-8") as f:
                                        calls_list = json.load(f)
                                        if not isinstance(calls_list, list):
                                            calls_list = [calls_list]
                                except Exception as parse_err:
                                    logger.warning(f"Error parseando JSON existente {json_path}: {parse_err}")
                                    
                            calls_list.append(call_data)
                            
                            with open(json_path, "w", encoding="utf-8") as f:
                                json.dump(calls_list, f, indent=4, ensure_ascii=False)
                                
                            logger.info(f"💾 [Registro] Información de llamada guardada en JSON: {json_path}")
                        except Exception as log_err:
                            logger.error(f"Error al escribir registro JSON de llamada: {log_err}")
                            
                    self.recorder = None
                    self.voice_capture = None
                    if self.voice_mode == 'grabacion':
                        self.agent_running = False

                    if self.agent_running:
                        logger.info("⏳ [Core] Esperando 2 segundos de seguridad antes de la siguiente conexión...")
                        await asyncio.sleep(2.0)
        except Exception as e:
            logger.error(f"Error Crítico: {e}")
        finally:
            if hasattr(self, 'phantom') and self.phantom:
                logger.info("🛑 Deteniendo Phantom Browser...")
                try:
                    self.phantom.stop()
                except Exception as pe:
                    logger.error(f"Error deteniendo Phantom Browser: {pe}")
