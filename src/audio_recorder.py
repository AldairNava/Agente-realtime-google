import wave
import audioop
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Graba toda la llamada (cliente + agente) en un solo archivo WAV."""

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
        logger.info(f"🎙️ [Grabación] Archivo: {self.call_path}")

    def write_client(self, pcm_data: bytes):
        """Graba audio del micrófono (ya viene a 16kHz)."""
        if self._is_open and pcm_data:
            try:
                # Evitar "not a whole number of frames" si por alguna razón llega un byte impar
                if len(pcm_data) % 2 != 0:
                    pcm_data = pcm_data[:-1]
                # Multiplicar el volumen del micrófono x4
                boosted_pcm = audioop.mul(pcm_data, 2, 4.0)
                self._wav.writeframes(boosted_pcm)
            except Exception as e:
                # Si falla matemáticamente, volver a escribir el original
                self._wav.writeframes(pcm_data)

    def write_agent(self, pcm_data: bytes):
        """Graba audio de la IA (viene a 24kHz, se resamplea a 16kHz)."""
        if self._is_open and pcm_data:
            # Convertir de 24kHz a 16kHz
            resampled, self._resample_state = audioop.ratecv(
                pcm_data, 2, 1,
                self.sample_rate_out, self.unified_rate,
                self._resample_state
            )
            self._wav.writeframes(resampled)

    def close(self):
        """Cierra el archivo WAV."""
        if not self._is_open:
            return
        self._is_open = False
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
