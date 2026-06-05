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

    async def _delayed_hangup_timer(self):
        wait_time = 5.0
        logger.info(f"⏳ [Cierre] Esperando {wait_time}s...")
        await asyncio.sleep(wait_time)
        if self.session_active and self.final_disposition:
            logger.warning(f"🛑 [Cierre] Enviando estatus: {self.final_disposition}")
            await asyncio.to_thread(self.tools_dispatcher.api.external_status, self.final_disposition)
            await asyncio.to_thread(self.tools_dispatcher.api.external_hangup)
            self.session_active = False

    async def _hangup_watchdog(self):
        # Esperar suficiente tiempo para que el PhantomBrowser complete el login en Vicidial
        # (navegar + paso1 + paso2 + seleccionar campaña + submit + disponible ≈ 30-40s)
        logger.info("⏳ [Watchdog] Esperando 60s para que el browser complete el login en Vicidial...")
        await asyncio.sleep(60)
        while self.session_active:
            try:
                import pymysql
                api_cfg = self.tools_dispatcher.api
                temp_conn = await asyncio.to_thread(
                    pymysql.connect, host=api_cfg.host, user='cron', 
                    password='1234', db='asterisk'
                )
                with temp_conn.cursor() as cursor:
                    query = "SELECT status FROM vicidial_live_agents WHERE user=%s LIMIT 1"
                    cursor.execute(query, (api_cfg.user,))
                    result = cursor.fetchone()
                    if not result:
                        logger.warning(f"⚠️ [Watchdog] Agente {api_cfg.user} desconectado. Cerrando.")
                        self.session_active = False
                        break
                temp_conn.close()
            except Exception as e:
                logger.error(f"Error Watchdog: {e}")
            await asyncio.sleep(5)

    async def _time_watchdog(self):
        logger.info("🕒 [Reloj] Iniciando watchdog de horario de trabajo...")
        last_action = None
        while self.agent_running:
            try:
                now = datetime.now()
                hour = now.hour
                
                # Caso 1: Hora de comida (entre las 2:00 PM y 3:00 PM -> 14:00:00 a 14:59:59)
                if 14 <= hour < 15:
                    if last_action != "break":
                        # Solo pausar si el login en el navegador ya se completó con éxito
                        if hasattr(self, 'phantom') and self.phantom and getattr(self.phantom, 'login_success', False):
                            api_cfg = self.tools_dispatcher.api
                            if api_cfg:
                                logger.info("🕒 [Reloj] Horario detectado entre 2 y 3 PM. Colocando agente en PAUSA con código BREAK...")
                                try:
                                    # 1. Enviar comando de pausa
                                    await asyncio.to_thread(api_cfg.external_pause, True)
                                    
                                    # 2. Esperar a que el agente esté realmente en estado PAUSED (máximo 5 segundos)
                                    agent_paused = False
                                    for attempt in range(5):
                                        await asyncio.sleep(1)
                                        status_data = await asyncio.to_thread(api_cfg.get_agent_status)
                                        current_status = status_data.get("status", "UNKNOWN")
                                        logger.info(f"🕒 [Reloj] Intento {attempt+1}: Estado actual de agente en Vicidial: {current_status}")
                                        if current_status == "PAUSED":
                                            agent_paused = True
                                            break
                                    
                                    # Si por alguna razón la consulta de estado falla/no marca PAUSED, igual procedemos tras el ciclo
                                    if not agent_paused:
                                        logger.warning("🕒 [Reloj] No se pudo confirmar estado PAUSED vía API tras el ciclo de espera. Procediendo de todos modos...")

                                    # 3. Intentar establecer el código de pausa
                                    code_set_success = False
                                    
                                    # Método A: Ejecutar JS en PhantomBrowser (el más seguro, simula click directo)
                                    if hasattr(self, 'phantom') and self.phantom:
                                        code_set_success = await asyncio.to_thread(self.phantom.set_pause_code, "Brake")
                                    
                                    # Método B: Fallback vía API de Vicidial
                                    if not code_set_success:
                                        logger.warning("🕒 [Reloj] Fallback: Intentando establecer código de pausa vía API...")
                                        res = await asyncio.to_thread(api_cfg.pause_code, "Brake")
                                        if "ERROR" in res:
                                            logger.warning(f"🕒 [Reloj] Error aplicando 'Brake' vía API: {res}. Reintentando con 'BREAK'...")
                                            res = await asyncio.to_thread(api_cfg.pause_code, "BREAK")
                                        logger.info(f"🕒 [Reloj] Resultado pause_code API: {res}")
                                        
                                    last_action = "break"
                                except Exception as pe:
                                    logger.error(f"Error aplicando pausa/break: {pe}")
                            
                # Caso 2: Fin de jornada (a partir de las 6:00 PM -> >= 18:00)
                elif hour >= 18:
                    api_cfg = self.tools_dispatcher.api
                    if api_cfg:
                        logger.warning("🕒 [Reloj] Fin de jornada detectado (después de las 6:00 PM). Iniciando cierre automático...")
                        try:
                            await asyncio.to_thread(api_cfg._call_api, "logout", {"value": "LOGOUT"})
                        except Exception as le:
                            logger.error(f"Error enviando comando de logout: {le}")
                        
                        self.agent_running = False
                        self.session_active = False
                        last_action = "logout"
                        
                        # Dar un breve tiempo para que finalicen las tareas y la conexión a Gemini
                        await asyncio.sleep(2)
                        
                        # Salida forzada para asegurar que no queden procesos o conexiones colgadas
                        logger.warning("🕒 [Reloj] Deteniendo proceso...")
                        os._exit(0)
                else:
                    # Fuera de horarios especiales, restablecer la última acción para permitir re-ejecución
                    if last_action == "break":
                        # Quitar pausa si volvemos del break
                        if hasattr(self, 'phantom') and self.phantom and getattr(self.phantom, 'login_success', False):
                            api_cfg = self.tools_dispatcher.api
                            if api_cfg:
                                logger.info("🕒 [Reloj] Fin del horario de comida. Quitando pausa al agente...")
                                try:
                                    await asyncio.to_thread(api_cfg.external_pause, False)
                                except Exception as re:
                                    logger.error(f"Error al quitar pausa al agente: {re}")
                        last_action = None
                        
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
                    # Muteado temporal de los primeros 3 segundos de habla de la IA para evitar interrupciones
                    is_muted = False
                    if getattr(self, '_ai_playback_active', False):
                        elapsed_speaking = asyncio.get_event_loop().time() - getattr(self, 'ai_speaking_start_time', 0)
                        if elapsed_speaking < 3.0:
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
                
                logger.info("⏱️ Retrasando ejecución de transfer_conference 6 segundos")
                # Wait up to 6 seconds in small chunks to detect session end
                for _ in range(12):
                    if not getattr(self, 'session_active', False):
                        logger.info("📞 Cliente colgó durante la despedida. Cortando retraso de transferencia.")
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
                        logger.info("🔊 [Audio] Agente comenzó a hablar. Muteando mic por 3s para evitar interrupciones.")

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

                # Paso 1: 30 segundos de silencio mutuo -> Primer aviso
                if elapsed >= 30.0 and getattr(self, 'silence_warnings_sent', 0) == 0:
                    logger.warning("⏱️ [Watchdog Silencio] 30s de silencio mutuo detectados. Enviando primer recordatorio al agente.")
                    self.silence_warnings_sent = 1
                    self.last_warning_sent_time = now
                    try:
                        await session.send_realtime_input(
                            text="[SISTEMA: El cliente no ha respondido por 30 segundos. Pregúntale brevemente si sigue ahí, por ejemplo: '¿Hola? ¿Sigue ahí?' o '¿Me escucha?']"
                        )
                        if hasattr(self, 'call_transcript'):
                            self.call_transcript.append("[Sistema] Primer aviso de silencio enviado al agente.")
                    except Exception as se:
                        logger.error(f"Error enviando recordatorio 1: {se}")

                # Paso 2: Otros 30 segundos (60s total) sin respuesta -> Segundo aviso
                elif getattr(self, 'silence_warnings_sent', 0) == 1 and (now - getattr(self, 'last_warning_sent_time', now)) >= 30.0:
                    logger.warning("⏱️ [Watchdog Silencio] Otros 30s de silencio (60s total). Enviando segundo recordatorio.")
                    self.silence_warnings_sent = 2
                    self.last_warning_sent_time = now
                    try:
                        await session.send_realtime_input(
                            text="[SISTEMA: El cliente sigue sin responder por 60 segundos en total. Pregúntale por última vez si sigue ahí, por ejemplo: '¿Hay alguien ahí?' o '¿Sigue en la línea?']"
                        )
                        if hasattr(self, 'call_transcript'):
                            self.call_transcript.append("[Sistema] Segundo aviso de silencio enviado al agente.")
                    except Exception as se:
                        logger.error(f"Error enviando recordatorio 2: {se}")

                # Paso 3: Otros 30 segundos (90s total) sin respuesta -> Colgar
                elif getattr(self, 'silence_warnings_sent', 0) == 2 and (now - getattr(self, 'last_warning_sent_time', now)) >= 30.0:
                    logger.warning("⏱️ [Watchdog Silencio] 90s de silencio mutuo continuo. Colgando por falta de respuesta...")
                    
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
        
        if self.campania_name in ('ventas_izzi', 'plata'):
            cierre_rules = (
                "\n2. CIERRE DE LLAMADA: Cuando el cliente esté calificado, interesado y confirme estar de acuerdo con ser transferido, haz lo siguiente en orden ESTRICTO:"
                "\n   a) Llama a la herramienta 'actualizar_comentarios_cliente' con los datos perfilados (nombre_cliente, pantallas, paquete_ofrecido, cuenta, dudas_no_respondidas). Hazlo en silencio, sin decírselo al cliente."
                "\n   b) Di DE VIVA VOZ tu frase de cierre de transferencia UNA SOLA VEZ (ej: 'Perfecto, un momento por favor, no cuelgue, lo transfiero con mi compañero...'). NO la repitas."
                "\n   c) Llama a la herramienta 'transfer_conference' con los parámetros: user='Virt1', password='Cyber123', ingrup='tvplus'."
                "\n   d) Inmediatamente después, llama a 'external_status' con el valor 'TRANSvent' (o 'transInt' si el cliente tenía dudas o preguntas específicas que no supiste responder y requirió transferencia inmediata)."
                "\n   PROHIBIDO: usar 'external_hangup' en este nodo, la transferencia se encargará del colgado."
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
                self.client_name = ""
                self.call_transcript = []
                self.last_client_speech_time = asyncio.get_event_loop().time()
                self.silence_warnings_sent = 0
                self.last_warning_sent_time = 0.0
                self.client_phone = ""
                self.client_cuenta = ""
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
                elif self.voice_mode in ('live', 'hibrido') and self.execution_mode == 'local':
                    from .audio_recorder import AgentVoiceCapture
                    session_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    # Guardar directo en la carpeta general recordings/ con su prefijo
                    recordings_dir = os.path.join(os.path.dirname(__file__), '..', 'recordings')
                    os.makedirs(recordings_dir, exist_ok=True)
                    capture_path = os.path.join(recordings_dir, f'live_session_{session_ts}.wav')
                    self.voice_capture = AgentVoiceCapture(output_path=capture_path)

                try:
                    async with self.client.aio.live.connect(model=model, config=config) as session:
                        logger.info("✅ Conexión establecida con Gemini. Esperando llamada...")
                        
                        async def monitor():
                            was_in_call = False
                            db_failed = False
                            while self.session_active:
                                try:
                                    status = None
                                    lead_id = None
                                    lead_id_str = ""
                                    first_name = ""
                                    last_name = ""
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
                                                            first_name = lead_res[0].strip() if lead_res[0] else ""
                                                            last_name = lead_res[1].strip() if lead_res[1] else ""
                                                            phone_number = lead_res[2].strip() if lead_res[2] else ""
                                            conn.close()
                                        except Exception as dbe:
                                            logger.warning(f"⚠️ [Monitor] Falló conexión a base de datos de Asterisk: {dbe}. Usando fallback de navegador...")
                                            db_failed = True
                                            
                                    # 2. Si no hay base de datos o falló, usar navegador
                                    if db_failed:
                                        if hasattr(self, 'phantom') and self.phantom:
                                            call_data = await asyncio.to_thread(self.phantom.get_active_call_data)
                                            phone_number = call_data.get("phone_number", "")
                                            first_name = call_data.get("first_name", "")
                                            last_name = call_data.get("last_name", "")
                                            cuenta = call_data.get("CUENTA", "")
                                            lead_id_str = call_data.get("lead_id", "")
                                            
                                            if phone_number or cuenta:
                                                is_hungup = await asyncio.to_thread(self.phantom.is_call_hungup)
                                                status = 'PAUSED' if is_hungup else 'INCALL'
                                            else:
                                                status = 'PAUSED'
                                        else:
                                            status = 'PAUSED'

                                    # 3. Procesar estado de llamada
                                    if status == 'INCALL':
                                        if not was_in_call:
                                            # Nueva llamada detectada. Asegurar que estamos en la pestaña SCRIPT
                                            if hasattr(self, 'phantom') and self.phantom:
                                                logger.info("👻 [Monitor] Nueva llamada. Activando pestaña SCRIPT en navegador...")
                                                if self.voice_mode != 'grabacion':
                                                    tasks.append(asyncio.create_task(self._silence_watchdog(session)))
                                                await asyncio.to_thread(self.phantom.go_to_script_tab)
                                                
                                                # Polling de hasta 4 segundos (en intervalos de 0.5s) esperando que cambie la cuenta
                                                # (o el teléfono en su defecto) y que tengamos un nombre de cliente real/válido (no genérico).
                                                new_client_found = False
                                                for i in range(8):
                                                    call_data = await asyncio.to_thread(self.phantom.get_active_call_data)
                                                    b_phone = call_data.get("phone_number", "")
                                                    b_first = call_data.get("first_name", "")
                                                    b_last = call_data.get("last_name", "")
                                                    b_cuenta = call_data.get("CUENTA", "")
                                                    b_lead_id = call_data.get("lead_id", "")
                                                    
                                                    # Determinar si el cliente/cuenta cambió respecto a la llamada anterior
                                                    has_change = False
                                                    if b_cuenta:
                                                        if b_cuenta != self.last_client_cuenta:
                                                            has_change = True
                                                    elif b_phone:
                                                        if b_phone != self.last_client_phone:
                                                            has_change = True
                                                            
                                                    if has_change:
                                                        # Comprobar si el nombre ya es válido (no genérico ni vacío)
                                                        is_valid = b_first and b_first.upper() not in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST", "")
                                                        
                                                        # Guardar datos temporales
                                                        phone_number = b_phone
                                                        first_name = b_first
                                                        last_name = b_last
                                                        cuenta = b_cuenta
                                                        lead_id_str = b_lead_id
                                                        
                                                        if is_valid:
                                                            new_client_found = True
                                                            logger.info(f"👻 [Monitor] Nuevo cliente válido detectado en intento {i+1}: cuenta={b_cuenta}, tel={b_phone}, nombre='{b_first}'")
                                                            break
                                                        else:
                                                            logger.info(f"👻 [Monitor] Intento {i+1}: Cliente detectado (cuenta={b_cuenta}, tel={b_phone}), pero el nombre sigue genérico ('{b_first}'). Esperando...")
                                                    await asyncio.sleep(0.5)
                                                
                                                if not new_client_found:
                                                    # Fallback tras expirar el polling (usar lo que se tenga)
                                                    call_data = await asyncio.to_thread(self.phantom.get_active_call_data)
                                                    b_phone = call_data.get("phone_number", "")
                                                    b_cuenta = call_data.get("CUENTA", "")
                                                    if b_cuenta or b_phone:
                                                        phone_number = b_phone
                                                        first_name = call_data.get("first_name", "")
                                                        last_name = call_data.get("last_name", "")
                                                        cuenta = b_cuenta
                                                        lead_id_str = call_data.get("lead_id", "")
                                                        logger.warning(f"👻 [Monitor] Expiró el tiempo de polling sin nombre válido. Usando: cuenta='{cuenta}', tel='{phone_number}', nombre='{first_name}'")
                                                
                                                # Una vez leídos los datos, regresar a la pestaña MAIN
                                                logger.info("👻 [Monitor] Datos leídos. Regresando a pestaña MAIN...")
                                                await asyncio.to_thread(self.phantom.go_to_main_tab)
                                            
                                            was_in_call = True
                                            self.call_start_time = asyncio.get_event_loop().time()  # Timestamp del inicio de llamada
                                            self.last_client_speech_time = asyncio.get_event_loop().time()
                                            self.silence_warnings_sent = 0
                                            self.client_name = f"{first_name} {last_name}".strip()
                                            self.client_phone = phone_number
                                            self.client_cuenta = cuenta
                                            self.client_lead_id = lead_id_str
                                            self.last_client_phone = phone_number  # Guardar el teléfono activo procesado
                                            self.last_client_cuenta = cuenta      # Guardar la cuenta activa procesada
                                            
                                            logger.info("📞 [Monitor] Llamada conectada. Cliente: %s | Tel: %s | Cuenta: %s", self.client_name, self.client_phone, self.client_cuenta)
                                            self.call_transcript.append(f"[Llamada Conectada] Cliente: {self.client_name}, Teléfono: {self.client_phone}, Cuenta: {self.client_cuenta}")
                                            
                                            is_valid_name = first_name and first_name.upper() not in ("TITULAR", "PROSPECTO", "CLIENTE", "DESCONOCIDO", "UNKNOWN", "TEST")
                                            if self.campania_name == 'ventas_izzi':
                                                if is_valid_name:
                                                    greeting_phrase = f"Buen día, ¿hablo con {first_name}?"
                                                else:
                                                    greeting_phrase = "Buen día, ¿hablo con el titular de la línea?"
                                            elif self.campania_name == 'retencion':
                                                greeting_phrase = "Buen día, gracias por llamar a cuentas especiales izzi, ¿con quién tengo el gusto?"
                                            else:
                                                if is_valid_name:
                                                    greeting_phrase = f"Buen día, me puede confirmar si ¿hablo con el señor(a) {first_name}?"
                                                else:
                                                    greeting_phrase = "Buen día, me puede confirmar si ¿hablo con el titular de la línea?"
                                            
                                            # Inyectar el contexto del cliente a Gemini
                                            await session.send_realtime_input(
                                                text=f"[SISTEMA: Llamada conectada. Cliente: {self.client_name or 'Desconocido'}. Teléfono: {self.client_phone}. Cuenta: {self.client_cuenta or 'Desconocido'}. IMPORTANTE: El saludo inicial de la llamada DEBE ser dicho de viva voz por ti: '{greeting_phrase}' ESPERA SU RESPUESTA. Si te preguntan quién habla, usa tu presentación completa y di que llamas de izzi.]"
                                            )
                                            
                                            # Y finalmente activar la llamada para desmutear/saludar
                                            self.vicidial_incall = True
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
                                await asyncio.sleep(1)

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
                            # Generar resumen asíncronamente
                            resumen = await self._generate_call_summary()
                            
                            today_str = datetime.now().strftime("%Y%m%d")
                            log_dir = os.path.join(os.path.dirname(__file__), '..', 'assets', self.campania_name, 'registro_de_llamadas')
                            os.makedirs(log_dir, exist_ok=True)
                            json_path = os.path.join(log_dir, f"{self.campania_name}_{today_str}.json")
                            txt_path = os.path.join(log_dir, f"{self.campania_name}_{today_str}.txt")
                            
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
                            # Si no existe el JSON pero sí el TXT viejo, hacer la migración para este día
                            if not os.path.exists(json_path) and os.path.exists(txt_path):
                                logger.info(f"Migrando registros existentes de {txt_path} a {json_path}...")
                                try:
                                    with open(txt_path, "r", encoding="utf-8") as f:
                                        for line in f:
                                            line_stripped = line.strip()
                                            if line_stripped:
                                                try:
                                                    calls_list.append(json.loads(line_stripped))
                                                except Exception:
                                                    pass
                                except Exception as mig_err:
                                    logger.error(f"Error migrando .txt a .json: {mig_err}")
                            
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
                            
                            # Eliminar .txt si existiera para que no quede duplicado
                            if os.path.exists(txt_path):
                                try:
                                    os.remove(txt_path)
                                except Exception:
                                    pass
                        except Exception as log_err:
                            logger.error(f"Error al escribir registro JSON de llamada: {log_err}")
                            
                    self.recorder = None
                    self.voice_capture = None
                    if self.voice_mode == 'grabacion':
                        self.agent_running = False
        except Exception as e:
            logger.error(f"Error Crítico: {e}")
        finally:
            if hasattr(self, 'phantom') and self.phantom:
                logger.info("🛑 Deteniendo Phantom Browser...")
                try:
                    self.phantom.stop()
                except Exception as pe:
                    logger.error(f"Error deteniendo Phantom Browser: {pe}")
