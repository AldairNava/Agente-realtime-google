import asyncio
import logging
import numpy as np
import pyVoIP
from pyVoIP.VoIP import VoIPPhone, CallState
import time
import socket

# Debug total de pyVoIP para diagnosticar el silencio
pyVoIP.debug = True

from .base import AudioInterface


logger = logging.getLogger(__name__)

class SipAudioInterface(AudioInterface):
    """
    Interfaz de Audio SIP:
    Registra el agente en Asterisk/Vicidial y maneja el flujo RTP.
    Realiza Resampling de 24kHz (Gemini) <-> 8kHz (SIP).
    """
    def __init__(self, server, port, user, password, chunk=512):
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.chunk = chunk  # Chunk para Gemini (512 @ 24kHz = 21.3ms)
        
        # Audio buffers
        self.in_buffer = bytearray()
        self.current_call = None
        self.is_running = True

        # Autodetectar la IP local que alcanza al servidor Asterisk
        try:
            s_ip = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s_ip.connect((self.server, 5060))
            local_ip = s_ip.getsockname()[0]
            s_ip.close()
        except:
            local_ip = "127.0.0.1"
            
        # Configurar Teléfono VoIP en puerto 5062 (evita conflicto con Zoiper/otro cliente en 5060)
        self.phone = VoIPPhone(
            self.server, self.port, self.user, self.password,
            callCallback=self._on_incoming_call,
            sipPort=5062,
            myIP=local_ip
        )

        logger.info(f"SIP: Intentando registro en {local_ip}:5062 para {self.user}@{self.server}...")
        self.phone.start()
        
        # Monitor de Registro + Polling de llamadas entrantes
        asyncio.create_task(self._registration_monitor())
        asyncio.create_task(self._call_poller())  # Polling activo (más confiable que callback en Windows)


    async def _registration_monitor(self):
        """Monitorea el registro SIP y reinicia pyVoIP si crashea (WinError 10038 en Windows)."""
        from pyVoIP.VoIP.status import PhoneStatus
        await asyncio.sleep(5)
        while self.is_running:
            try:
                status = self.phone.get_status()
                if status == PhoneStatus.REGISTERED:
                    logger.info(f"✅ [SIP] Registro ACTIVO para {self.user}")
                elif status == PhoneStatus.FAILED:
                    logger.warning(f"⚠️ [SIP] Estado FAILED detectado. Reiniciando pyVoIP...")
                    await self._restart_phone()
                else:
                    logger.warning(f"❌ [SIP] Estado: {status}. Esperando...")
            except Exception as e:
                logger.error(f"❌ [SIP] Error en monitor: {e}. Reiniciando...")
                await self._restart_phone()
            await asyncio.sleep(10)

    async def _restart_phone(self):
        """Reinicia el teléfono pyVoIP cuando crashea con WinError 10038."""
        try:
            if self.phone:
                try:
                    self.phone.stop()
                except Exception:
                    pass
        except Exception:
            pass

        await asyncio.sleep(3)

        try:
            import socket as _socket
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.connect((self.server, self.port))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"

        try:
            self.phone = VoIPPhone(
                self.server, self.port, self.user, self.password,
                callCallback=self._on_incoming_call,
                sipPort=5062,
                myIP=local_ip
            )
            self.phone.start()
            logger.info(f"🔄 [SIP] pyVoIP reiniciado. Registrando {self.user}@{self.server}...")
        except Exception as e:
            logger.error(f"❌ [SIP] Error al reiniciar pyVoIP: {e}")

    async def _call_poller(self):
        """
        Revisa activamente el diccionario de llamadas de pyVoIP cada 500ms.
        Esto es un mecanismo de respaldo ya que el callCallback de pyVoIP
        es inestable en Windows (no siempre se dispara).
        """
        await asyncio.sleep(3)  # Esperar que pyVoIP arranque
        seen_calls = set()
        while self.is_running:
            try:
                active_calls = self.phone.get_calls()
                for call_id, call in list(active_calls.items()):
                    if call_id not in seen_calls:
                        seen_calls.add(call_id)
                        logger.warning(f"📞 [SIP][POLL] Llamada detectada por polling: {call_id}")
                        # Contestar en un hilo separado para no bloquear el loop
                        import threading
                        threading.Thread(
                            target=self._answer_call_sync, args=(call,), daemon=True
                        ).start()
                # Limpiar IDs de llamadas ya terminadas
                seen_calls = seen_calls.intersection(set(active_calls.keys()))
            except Exception as e:
                pass  # Ignorar errores de polling (ocurren cuando pyVoIP se reinicia)
            await asyncio.sleep(0.5)

    def _answer_call_sync(self, call):
        """Contesta una llamada de forma sincrónica desde un hilo separado."""
        import time as _time
        try:
            caller = call.request.headers.get('From', '?')
        except Exception:
            caller = '?'
        logger.warning(f"📞 [SIP] Auto-contestando llamada de: {caller}")
        for intento in range(5):
            try:
                call.answer()
                self.current_call = call
                logger.info(f"✅ [SIP] Llamada CONTESTADA (intento {intento+1})")
                try:
                    call.write_audio(b'\x00' * 160)
                    logger.info("🔔 [SIP] Canal RTP abierto.")
                except Exception:
                    pass
                return
            except Exception as e:
                logger.warning(f"⚠️ [SIP] Error al contestar (intento {intento+1}): {e}")
                _time.sleep(0.5)
        logger.error("❌ [SIP] No se pudo contestar la llamada.")

    def _on_incoming_call(self, call):
        """Callback cuando entra una llamada SIP. Contesta automáticamente."""
        try:
            caller = call.request.headers.get('From', 'Desconocido')
        except Exception:
            caller = 'Desconocido'
        logger.warning(f"📞 [SIP] *** LLAMADA ENTRANTE de: {caller} ***")
        
        self.current_call = call
        
        # Intentar contestar con reintentos
        answered = False
        for intento in range(5):
            try:
                self.current_call.answer()
                answered = True
                logger.info(f"✅ [SIP] Llamada CONTESTADA (intento {intento+1}).")
                break
            except Exception as e:
                logger.warning(f"⚠️ [SIP] Error al contestar (intento {intento+1}): {e}")
                time.sleep(0.5)
        
        if not answered:
            logger.error("❌ [SIP] No se pudo contestar la llamada después de 5 intentos.")
            return

        # Señal de presencia: frame de silencio para abrir el canal RTP
        try:
            self.current_call.write_audio(b'\x00' * 160)
            logger.info("🔔 [SIP] Canal RTP abierto. Streaming iniciado.")
        except Exception as e:
            logger.warning(f"⚠️ [SIP] Error enviando señal de presencia: {e}")


    def dial(self, number):
        """Marca a un número (ej. sala de conferencia) para entrar al juego."""
        logger.info(f"🏟️ [SIP] Marcando a la sala: {number}...")
        self.current_call = self.phone.call(number)
        
        # Mandar señal para despertar la sala de conferencia
        async def send_wakeup():
            await asyncio.sleep(3)
            if self.current_call:
                logger.info("🔔 [SIP] Intentando activar audio con señal de presencia...")
                # Mandar un pequeño frame de audio para 'despertar' el bridge
                self.current_call.write_audio(b'\x00' * 160) 
        
        # Iniciar la tarea de despertar
        import asyncio
        asyncio.create_task(send_wakeup())
        logger.info(f"✅ [SIP] Llamada a {number} iniciada.")


    async def read_chunk(self) -> bytes:
        """
        Lee audio del SIP (8kHz), lo escala a 16kHz y garantiza un tamaño de chunk constante para Gemini/VAD.
        """
        last_log_time = 0
        while self.is_running:
            now = time.time()
            if not self.current_call:
                if now - last_log_time > 5:
                    logger.debug("⏳ [SIP] Sin llamada activa. Esperando...")
                    last_log_time = now
                await asyncio.sleep(0.1)
                continue

            if self.current_call.state != CallState.ANSWERED:
                if now - last_log_time > 2:
                    logger.warning(f"⚠️ [SIP] Llamada en estado: {self.current_call.state}. Esperando audio...")
                    last_log_time = now
                await asyncio.sleep(0.1)
                continue
            
            sip_samples_needed = self.chunk // 2
            try:
                data = await asyncio.to_thread(self.current_call.read_audio, sip_samples_needed)
            except Exception as e:
                logger.error(f"Error reading SIP audio: {e}")
                data = None
            
            if not data:
                await asyncio.sleep(0.01)
                continue
            
            if now - last_log_time > 5:
                logger.info(f"👂 [SIP] Recibiendo audio del servidor ({len(data)} bytes)...")
            
            import audioop
            # 1. Decodificar PCMU (8-bit) de pyVoIP a Linear PCM (16-bit)
            try:
                pcm_16bit = audioop.ulaw2lin(data, 2)
                # 2. Upsampling simple (Repetición x2) para pasar de 8k a 16k
                samples_8k = np.frombuffer(pcm_16bit, dtype=np.int16)
                samples_16k = np.repeat(samples_8k, 2)
                
                self.in_buffer.extend(samples_16k.tobytes())
            except Exception as e:
                logger.error(f"Error transformando audio: {e}")
            
            # Solo entregar si tenemos al menos el tamaño del chunk solicitado
            chunk_bytes = self.chunk * 2 # 16-bit = 2 bytes per sample
            if len(self.in_buffer) >= chunk_bytes:
                ret = bytes(self.in_buffer[:chunk_bytes])
                self.in_buffer = self.in_buffer[chunk_bytes:]
                return ret


    async def write_chunk(self, data: bytes):
        """
        Recibe audio de Gemini (24kHz), lo reduce a 8kHz y lo codifica a PCMU para el SIP.
        """
        if not self.current_call or self.current_call.state != CallState.ANSWERED:
            return

        import audioop
        # Gemini envía muestras a 24kHz. Necesitamos bajar a 8kHz.
        samples_24k = np.frombuffer(data, dtype=np.int16)
        
        # Downsampling simple (Tomar 1 de cada 3)
        samples_8k = samples_24k[::3]
        
        # Codificar Linear PCM (16-bit) a PCMU (8-bit) para Asterisk
        try:
            pcmu_8bit = audioop.lin2ulaw(samples_8k.tobytes(), 2)
            # Escribir al stream de pyVoIP en un hilo separado
            await asyncio.to_thread(self.current_call.write_audio, pcmu_8bit)
        except Exception as e:
            logger.error(f"Error codificando audio a PCMU: {e}")

    def close(self):
        """Cierra el teléfono SIP de forma segura y desregistra al agente"""
        logger.info("🛑 [SIP] Desconectando y liberando puertos...")
        self.is_running = False
        try:
            if hasattr(self, 'current_call') and self.current_call:
                try:
                    # Intentar colgar de forma asíncrona pero segura
                    self.current_call.hangup()
                except:
                    pass
            
            if hasattr(self, 'phone') and self.phone:
                try:
                    self.phone.stop()
                except Exception as e:
                    # Ignorar error 10038 si el socket ya está cerrado
                    if "10038" not in str(e):
                        logger.warning(f"⚠️ [SIP] Error al detener teléfono: {e}")
        except Exception as e:
            logger.warning(f"⚠️ [SIP] Error general en cierre: {e}")
        finally:
            self.phone = None
            self.current_call = None
            logger.info("🛑 [SIP] Estadio vacío. Puertos liberados.")
