import wave
import audioop
import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Graba toda la llamada (cliente + agente) en un solo archivo WAV mezclado."""

    def __init__(self, output_dir="recordings", sample_rate_in=16000, sample_rate_out=24000):
        self.output_dir = output_dir
        self.sample_rate_in = sample_rate_in
        self.sample_rate_out = sample_rate_out
        self.unified_rate = sample_rate_in  # Todo se normaliza a 16kHz
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        os.makedirs(output_dir, exist_ok=True)

        self.call_path = os.path.join(output_dir, f"{self.session_id}_llamada.wav")

        self._wav = wave.open(self.call_path, 'wb')
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)  # 16-bit PCM
        self._wav.setframerate(self.unified_rate)

        # Estado para el resampler del audio del agente (24k → 16k)
        self._resample_state = None

        self._is_open = True
        self._agent_buffer = bytearray()
        self._lock = threading.Lock()
        logger.info(f"🎙️ [Grabación] Archivo: {self.call_path}")

    def write_client(self, pcm_data: bytes):
        """Graba audio del micrófono (ya viene a 16kHz), mezclándolo con el del agente."""
        if not self._is_open or not pcm_data:
            return

        # Evitar "not a whole number of frames" si por alguna razón llega un byte impar
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]

        try:
            # Multiplicar el volumen del micrófono x4
            boosted_pcm = audioop.mul(pcm_data, 2, 4.0)
        except Exception:
            boosted_pcm = pcm_data

        # Obtener la misma cantidad de bytes del buffer del agente
        with self._lock:
            buffer_len = len(self._agent_buffer)
            needed_len = len(boosted_pcm)
            
            if buffer_len >= needed_len:
                agent_pcm = bytes(self._agent_buffer[:needed_len])
                del self._agent_buffer[:needed_len]
            elif buffer_len > 0:
                agent_pcm = bytes(self._agent_buffer) + b'\x00' * (needed_len - buffer_len)
                self._agent_buffer.clear()
            else:
                agent_pcm = None

        if agent_pcm:
            try:
                # Mezclar ambos audios usando audioop.add
                mixed_pcm = audioop.add(boosted_pcm, agent_pcm, 2)
                self._wav.writeframes(mixed_pcm)
            except Exception as e:
                logger.error(f"Error mezclando audio: {e}")
                self._wav.writeframes(boosted_pcm)
        else:
            self._wav.writeframes(boosted_pcm)

    def write_agent(self, pcm_data: bytes):
        """Recibe el audio de la IA, lo resamplea a 16kHz y lo añade al buffer para mezclarlo."""
        if not self._is_open or not pcm_data:
            return

        try:
            # Convertir de 24kHz a 16kHz
            resampled, self._resample_state = audioop.ratecv(
                pcm_data, 2, 1,
                self.sample_rate_out, self.unified_rate,
                self._resample_state
            )
            with self._lock:
                self._agent_buffer.extend(resampled)
        except Exception as e:
            logger.error(f"Error resampleando audio del agente: {e}")

    def close(self):
        """Cierra el archivo WAV, escribiendo lo que quede en el buffer."""
        if not self._is_open:
            return
        self._is_open = False
        
        # Escribir cualquier residuo del agente que haya quedado en el buffer
        with self._lock:
            if self._agent_buffer:
                try:
                    self._wav.writeframes(bytes(self._agent_buffer))
                except Exception:
                    pass
                self._agent_buffer.clear()

        self._wav.close()
        size_kb = os.path.getsize(self.call_path) / 1024
        logger.info(f"💾 [Grabación] {self.call_path} ({size_kb:.0f} KB) guardado.")


class AgentVoiceCapture:
    """
    Captura exclusivamente la voz del agente IA en calidad nativa 24kHz.
    Ideal para grabar sesiones --live y reutilizarlas como audios pregrabados.
    El archivo resultante es compatible directamente con los pregrabados del sistema.
    """

    def __init__(self, output_path: str, sample_rate: int = 24000):
        self.output_path = output_path
        self.sample_rate = sample_rate
        self._resample_state = None
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        self._wav = wave.open(output_path, 'wb')
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)  # 16-bit PCM
        self._wav.setframerate(sample_rate)
        self._is_open = True
        logger.info(f"🎤 [Captura Live] Iniciando captura de voz del agente → {output_path}")

    def write(self, pcm_data: bytes):
        """Escribe PCM del agente directamente (24kHz, sin resamplear)."""
        if self._is_open and pcm_data:
            self._wav.writeframes(pcm_data)

    def close(self):
        """Cierra y guarda el archivo WAV."""
        if not self._is_open:
            return
        self._is_open = False
        self._wav.close()
        size_kb = os.path.getsize(self.output_path) / 1024
        logger.info(f"💾 [Captura Live] Guardado: {self.output_path} ({size_kb:.1f} KB)")
