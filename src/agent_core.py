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
        
        # Cargar configuración central
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'voice_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_cfg = json.load(f)

        # Validar y cargar perfil de campaña
        if campania not in self.full_cfg.get('campaigns', {}):
            raise ValueError(f"La campaña '{campania}' no existe en voice_config.json")
        
        self.campania_cfg = self.full_cfg['campaigns'][campania]
        # Inyectar configuraciones de campaña en un objeto de configuración activa
        # Esto permite que el resto del código siga funcionando con self.voice_cfg
        self.voice_cfg = {**self.full_cfg.get('common_settings', {}), **self.campania_cfg}
        
        # Especial: unificar vicidial_api para el ToolDispatcher SOLO en producción
        if self.execution_mode == 'produccion':
            self.voice_cfg['vicidial_api'] = {
                **self.full_cfg.get('vicidial_api', {}), # Base global (host, etc)
                **self.campania_cfg.get('vicidial_api', {}) # Overrides específicos
            }
        else:
            self.voice_cfg['vicidial_api'] = None
            logger.info("🛠️ [Local] Herramientas de Vicidial DESACTIVADAS por modo local.")

        # Inyectar interfaz de audio o usar local por defecto
        self.audio_interface = audio_interface or LocalAudioInterface(chunk=512)
        self.vad = VADProcessor()

        # --- AUDIO ROUTER (Dinámico por Campaña) ---
        scripts_file = self.campania_cfg.get('scripts_file', 'retention_scripts.json')
        scripts_path = os.path.join(os.path.dirname(__file__), '..', 'config', scripts_file)
        self.audio_router = AudioRouter(api_key=api_key, scripts_path=scripts_path)

        # Tools Base
        extra_tools = [self.fijar_estatus_final]
        
        # Modo Híbrido: Solo si el modo es hibrido, activamos pregrabados
        if self.voice_mode == 'hibrido':
            extra_tools.append(self.audio_router.reproducir_audio_pregrabado)
            logger.info(f"🔊 [Híbrido] Herramienta de audios pregrabados ACTIVADA ({scripts_file}).")
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
        rec_cfg = self.voice_cfg.get('recording', {})
        if rec_cfg.get('enabled'):
            self.recorder = AudioRecorder(output_dir='recordings')
        else:
            self.recorder = None

        # Captura exclusiva (Modo Grabación o Live Reuse)
        self.voice_capture = None
        if self.voice_mode in ('live', 'grabacion', 'hibrido'):
            if self.voice_mode == 'grabacion':
                # Leer texto desde el archivo .txt de la campaña
                if self.grabacion_txt:
                    textos_dir = os.path.join(os.path.dirname(__file__), '..', 'config', f'textos_audios_{campania}')
                    txt_path = os.path.join(textos_dir, f"{self.grabacion_txt}.txt")
                    if not os.path.exists(txt_path):
                        logger.error(f"❌ [Modo Grabación] Archivo no encontrado: {txt_path}")
                        sys.exit(1)
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        self.grabacion_frase = f.read().strip()
                    self.grabacion_salida = self.grabacion_txt + ".wav"
                    logger.info(f"✨ [Modo Grabación] .txt leído: '{self.grabacion_txt}' → \"{self.grabacion_frase[:60]}...\"")
                
                capture_path = os.path.join(self.capture_dir, self.grabacion_salida if self.grabacion_salida.endswith('.wav') else self.grabacion_salida + '.wav')
            else:
                session_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                capture_path = os.path.join(self.capture_dir, f'live_session_{session_ts}.wav')
            
            self.voice_capture = AgentVoiceCapture(output_path=capture_path)
            logger.info(f"🎤 [Captura Voz] Guardando en: {capture_path}")

        # --- ESTADO Y MONITOREO ---
        self.final_disposition = None
        self.session_active = True
        self.delayed_hangup_task = None
        self.audio_out_queue = asyncio.Queue()
        self.greeting_done = False
        self.greeting_lock = False
        self.ai_speaking = False
        self.vicidial_logged_in = False
        self.client_phone = self.voice_cfg.get('current_call', {}).get('client_phone', '')
        self.client_name = ''

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
        await asyncio.sleep(10)
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

    async def _send_audio(self, session):
        try:
            while self.session_active:
                chunk = await self.audio_interface.read_chunk()
                if hasattr(self, 'vicidial_incall') and not self.vicidial_incall:
                    continue

                if not getattr(self, '_greeting_triggered', False):
                    self._greeting_triggered = True
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

                if self.vad.is_speech(chunk) and self.delayed_hangup_task:
                    self.delayed_hangup_task.cancel()
                    self.delayed_hangup_task = None

                if self.recorder: self.recorder.write_client(chunk)
                await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm"))
        except Exception as e:
            if "1000" not in str(e): logger.error(f"Error _send_audio: {e}")

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
                    if response.text: logger.info(f"🤖 [IA]: {response.text}")
                    if response.tool_call:
                        for fc in response.tool_call.function_calls:
                            asyncio.create_task(self._process_tool_call(session, fc))
        except Exception as e:
            if "1000" not in str(e): logger.error(f"Error Gemini Session: {e}")

    async def _process_tool_call(self, session, fc):
        try:
            result = await asyncio.to_thread(self.tools_dispatcher.execute_tool, fc.name, fc.args)
            if fc.name == 'reproducir_audio_pregrabado' and self.voice_mode == 'hibrido':
                pending = getattr(self.audio_router, '_pending_playback', None)
                if pending:
                    self.audio_router._pending_playback = None
                    asyncio.create_task(self._inject_prerecorded_audio(pending['script_id'], pending.get('variables', {})))
            await session.send_tool_response(function_responses=[types.FunctionResponse(name=fc.name, response=result, id=fc.id)])
        except Exception as e:
            logger.error(f"Error Tool {fc.name}: {e}")
            await session.send_tool_response(function_responses=[types.FunctionResponse(name=fc.name, response={"error": str(e)}, id=fc.id)])

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
        while self.session_active:
            try:
                data = await asyncio.wait_for(self.audio_out_queue.get(), timeout=1.0)
                if self.recorder: self.recorder.write_agent(data)
                if self.voice_capture: self.voice_capture.write(data)
                await self.audio_interface.write_chunk(data)
                if self.audio_out_queue.empty():
                    self.ai_speaking = False
                    if self.greeting_lock: self.greeting_lock = False
                    if not self.greeting_done: self.greeting_done = True
            except asyncio.TimeoutError: continue

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
        if self.voice_mode == 'hibrido':
            available = self.audio_router.get_available_scripts()
            pregrabados_block = "AUDIOS PREGRABADOS DISPONIBLES (Usa 'reproducir_audio_pregrabado'): "
            for sid, info in available.items():
                pregrabados_block += f"'{sid}': \"{info['text'][:50]}...\"; "
        
        full_prompt = f"{personality} ROL: {role_block} IDENTIDAD: {identity_rules} FLUJO: {flow_block} REGLAS: {rules_block} {pregrabados_block}"

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
        try:
            async with self.client.aio.live.connect(model=model, config=config) as session:
                logger.info("✅ Conexión establecida con Gemini.")
                self.session_active = True
                
                # Logueo en Vicidial si es producción
                if hasattr(self.audio_interface, 'phone'):
                    from src.phantom_browser import PhantomAgent
                    api_cfg = self.tools_dispatcher.api
                    self.phantom = PhantomAgent(api_cfg.host, api_cfg.phone_login, api_cfg.phone_pass, api_cfg.user, api_cfg.password, api_cfg.campaign_id)
                    await asyncio.sleep(2)
                    self.phantom.start()
                    self.vicidial_incall = False
                    
                    async def monitor():
                        while self.session_active:
                            try:
                                import pymysql
                                conn = await asyncio.to_thread(pymysql.connect, host=api_cfg.host, user='cron', password='1234', db='asterisk')
                                with conn.cursor() as cur:
                                    cur.execute("SELECT status FROM vicidial_live_agents WHERE user=%s", (api_cfg.user,))
                                    res = cur.fetchone()
                                    if res and res[0] == 'INCALL': self.vicidial_incall = True
                                    else: self.vicidial_incall = False
                                conn.close()
                            except: pass
                            await asyncio.sleep(1)
                    asyncio.create_task(monitor())

                tasks = [
                    asyncio.create_task(self._send_audio(session)),
                    asyncio.create_task(self._receive_responses(session)),
                    asyncio.create_task(self._play_audio())
                ]
                if hasattr(self.audio_interface, 'phone'): tasks.append(asyncio.create_task(self._hangup_watchdog()))

                while self.session_active: await asyncio.sleep(1)
                for t in tasks: t.cancel()
        except Exception as e:
            logger.error(f"Error Crítico: {e}")
