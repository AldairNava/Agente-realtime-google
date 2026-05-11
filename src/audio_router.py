"""
Audio Router — Motor Híbrido Multi-Campaña
==========================================
Motor universal que sirve audios pregrabados para cualquier tipo de llamada.
Capa 1: Audios pregrabados (WAV) para frases estándar del guion
Capa 2: Gemini TTS bajo demanda para frases con variables dinámicas
Capa 3: Gemini Live API para respuestas completamente improvisadas (manejada por agent_core)

Soporta múltiples catálogos: retention_scripts.json, amex_scripts.json, etc.
El catálogo se selecciona en agent_core según active_call_type.
"""

import os
import json
import wave
import asyncio
import logging
import hashlib
import random
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class AudioRouter:
    """
    Decide si reproducir un WAV pregrabado o generar audio con TTS bajo demanda.
    Los audios pregrabados se sirven instantáneamente (0 latencia).
    Los dinámicos se generan con gemini-2.5-flash-preview-tts y se cachean.
    """

    def __init__(self, api_key: str, scripts_path: str = None, audio_dir: str = None):
        self.client = genai.Client(api_key=api_key)
        
        # Rutas por defecto
        base_dir = os.path.join(os.path.dirname(__file__), '..')
        self.scripts_path = scripts_path or os.path.join(base_dir, 'config', 'retention_scripts.json')
        
        # Cargar catálogo
        with open(self.scripts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.tts_config = data.get('tts_config', {})
        self.scripts = data.get('scripts', {})
        self.model = self.tts_config.get('model', 'gemini-2.5-flash-preview-tts')
        self.voice_name = self.tts_config.get('voice_name', 'Kore')
        self.audio_profile = self.tts_config.get('audio_profile', '')
        
        config_dir = self.tts_config.get('output_dir', 'recordings/pregrabados')
        self.audio_dir = audio_dir or os.path.join(base_dir, *config_dir.replace('\\', '/').split('/'))
        
        # Crear directorio de pregrabados si no existe
        os.makedirs(self.audio_dir, exist_ok=True)
        
        # Cache en memoria: script_id -> PCM bytes
        self._cache = {}
        
        # Pre-cargar WAVs pregrabados existentes
        self._preload_existing()
        
        logger.info(
            f"🎙️ [AudioRouter] Inicializado. "
            f"Scripts: {len(self.scripts)} | "
            f"Pregrabados cargados: {len(self._cache)} | "
            f"Voz: {self.voice_name} | Modelo TTS: {self.model}"
        )

    def _preload_existing(self):
        """Carga a memoria todos los WAV pregrabados existentes."""
        for script_id, script in self.scripts.items():
            if not script.get('prerecord', False):
                continue
            wav_path = os.path.join(self.audio_dir, f"{script_id}.wav")
            if os.path.exists(wav_path):
                try:
                    with wave.open(wav_path, 'rb') as wf:
                        pcm_data = wf.readframes(wf.getnframes())
                    self._cache[script_id] = pcm_data
                except Exception as e:
                    logger.warning(f"⚠️ [AudioRouter] Error cargando {wav_path}: {e}")

    def get_script_info(self, script_id: str) -> dict:
        """Devuelve la metadata de un script (para que Gemini sepa qué hay disponible)."""
        return self.scripts.get(script_id, {})

    def get_available_scripts(self) -> dict:
        """Lista todos los scripts disponibles con su categoría (para inyectar en prompt)."""
        result = {}
        for sid, script in self.scripts.items():
            result[sid] = {
                'category': script.get('category', ''),
                'text': script.get('text', ''),
                'has_variables': len(script.get('variables', [])) > 0,
                'variables': script.get('variables', []),
            }
        return result

    def is_prerecorded(self, script_id: str) -> bool:
        """Verifica si un script tiene WAV pregrabado listo."""
        return script_id in self._cache

    async def get_audio(self, script_id: str, variables: dict = None) -> bytes | None:
        """
        Punto de entrada principal. Obtiene PCM para un script_id.
        
        Si existen variantes del script (ej: ret_saludo_v2, ret_saludo_v3),
        elige una al azar para sonar más natural en cada llamada.
        
        - Si es pregrabado y está en cache → retorna instantáneo
        - Si tiene variables → genera con TTS bajo demanda y cachea
        - Si no existe → retorna None (la Live API se encarga)
        """
        if script_id not in self.scripts:
            logger.warning(f"⚠️ [AudioRouter] Script '{script_id}' no encontrado en el catálogo")
            return None

        # --- Selección aleatoria de variantes ---
        # Busca ret_saludo_v2, ret_saludo_v3... y elige al azar junto con el original
        variantes = [script_id]
        i = 2
        while True:
            candidato = f"{script_id}_v{i}"
            if candidato in self.scripts:
                variantes.append(candidato)
                i += 1
            else:
                break
        
        selected_id = random.choice(variantes)
        if len(variantes) > 1:
            logger.info(f"🎲 [AudioRouter] Variantes disponibles para '{script_id}': {variantes} → eligiendo '{selected_id}'")
        
        script_id = selected_id
        script = self.scripts[script_id]
        required_vars = script.get('variables', [])

        # Caso 1: Sin variables y pregrabado → sirve del cache
        if not required_vars and script_id in self._cache:
            logger.info(f"🎙️ [AudioRouter] Sirviendo pregrabado: {script_id}")
            return self._cache[script_id]

        # Caso 2: Sin variables pero no en cache → genera y cachea
        if not required_vars:
            logger.info(f"🔄 [AudioRouter] Generando pregrabado ausente: {script_id}")
            pcm = await self._generate_tts(script)
            if pcm:
                self._cache[script_id] = pcm
                self._save_wav(script_id, pcm)
            return pcm

        # Caso 3: Con variables → generar TTS dinámico
        if variables is None:
            variables = {}
        
        # Verificar que todas las variables requeridas estén presentes
        missing = [v for v in required_vars if v not in variables]
        if missing:
            logger.error(f"❌ [AudioRouter] Variables faltantes para '{script_id}': {missing}")
            return None

        # Construir cache key con variables
        cache_key = self._make_cache_key(script_id, variables)
        if cache_key in self._cache:
            logger.info(f"🎙️ [AudioRouter] Sirviendo TTS cacheado: {script_id} ({variables})")
            return self._cache[cache_key]

        # Generar audio dinámico con variables interpoladas
        interpolated_script = dict(script)
        text = script['text']
        for var_name, var_value in variables.items():
            text = text.replace(f'{{{var_name}}}', str(var_value))
        interpolated_script['text'] = text

        logger.info(f"⚡ [AudioRouter] Generando TTS dinámico: {script_id} → '{text[:60]}...'")
        pcm = await self._generate_tts(interpolated_script)
        if pcm:
            self._cache[cache_key] = pcm
            # Guardar con nombre que incluya hash para no saturar disco
            self._save_wav(f"{script_id}_{cache_key[:8]}", pcm)
        return pcm

    async def _generate_tts(self, script: dict) -> bytes | None:
        """Genera audio usando Gemini TTS API (generate_content con modalidad AUDIO)."""
        text = script.get('text', '')
        direction = script.get('tts_direction', '')
        
        # Construir prompt con Audio Profile + dirección
        prompt = f"{self.audio_profile}\n\n{direction} \"{text}\""

        try:
            config = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.voice_name
                        )
                    )
                ),
            )

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
                config=config,
            )

            # Extraer datos de audio PCM
            if (response.candidates 
                and response.candidates[0].content 
                and response.candidates[0].content.parts):
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        logger.info(f"✅ [TTS] Audio generado: {len(part.inline_data.data)} bytes")
                        return part.inline_data.data

            logger.warning("⚠️ [TTS] Respuesta sin datos de audio")
            return None

        except Exception as e:
            logger.error(f"❌ [TTS] Error generando audio: {e}")
            return None

    def _save_wav(self, filename: str, pcm_data: bytes):
        """Guarda PCM como archivo WAV."""
        wav_path = os.path.join(self.audio_dir, f"{filename}.wav")
        try:
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(self.tts_config.get('channels', 1))
                wf.setsampwidth(self.tts_config.get('sample_width', 2))
                wf.setframerate(self.tts_config.get('sample_rate', 24000))
                wf.writeframes(pcm_data)
            logger.info(f"💾 [AudioRouter] WAV guardado: {wav_path}")
        except Exception as e:
            logger.error(f"❌ [AudioRouter] Error guardando WAV: {e}")

    def _make_cache_key(self, script_id: str, variables: dict) -> str:
        """Genera un hash determinista para variables."""
        raw = f"{script_id}:" + ":".join(f"{k}={v}" for k, v in sorted(variables.items()))
        return hashlib.md5(raw.encode()).hexdigest()

    # ── Herramienta expuesta a Gemini ──
    def reproducir_audio_pregrabado(self, script_id: str, variables: str = "") -> str:
        """
        Herramienta que Gemini puede llamar para reproducir un audio pregrabado
        del catálogo de retención en vez de generar la respuesta con su propia voz.
        
        Args:
            script_id: ID del audio a reproducir (ej: 'saludo_generico', 'momento_por_favor')
            variables: Variables en formato 'key=value,key2=value2' (solo para scripts dinámicos)
        
        Returns:
            Confirmación de que el audio fue encolado para reproducción.
        """
        if script_id not in self.scripts:
            return f"Error: Script '{script_id}' no existe en el catálogo."
        
        # Parsear variables si las hay
        var_dict = {}
        if variables:
            for pair in variables.split(','):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    var_dict[k.strip()] = v.strip()
        
        # La ejecución real del audio se hace en agent_core al procesar el tool response
        # Aquí solo validamos y retornamos el resultado
        script = self.scripts[script_id]
        
        # Marcar en un atributo la solicitud pendiente para que agent_core la procese
        self._pending_playback = {
            'script_id': script_id,
            'variables': var_dict,
            'text': script['text'],
        }
        
        return f"OK. Audio '{script_id}' encolado para reproducción. NO repitas este texto con tu propia voz, el sistema lo reproducirá automáticamente."
