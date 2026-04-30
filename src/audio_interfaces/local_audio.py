import pyaudio
import asyncio
import logging
import os
logger = logging.getLogger(__name__)

from .base import AudioInterface

class LocalAudioInterface(AudioInterface):
    """
    Especialista de Audio & Asincronismo:
    Maneja PyAudio mediante `to_thread` liberando completamente el loop de WebSockets
    evitando tartamudeos en la capa de red IA.
    """
    def __init__(self, sample_rate=16000, channels=1, chunk=512):
        self.sample_rate = sample_rate
        self.channels = channels
        # Silero VAD exige bloques estables de 512 frames (32ms en 16Khz)
        self.chunk = chunk 
        self.p_audio = pyaudio.PyAudio()
        self.is_running = True
        
        mic_index_env = os.getenv("MICROPHONE_INDEX")
        try:
            if mic_index_env is not None:
                self.stream_in = self.p_audio.open(
                    format=pyaudio.paInt16, channels=self.channels, rate=self.sample_rate,
                    input=True, frames_per_buffer=self.chunk, input_device_index=int(mic_index_env)
                )
                logger.info(f"Usando Micrófono especificado en .env (Index: {mic_index_env})")
            else:
                self.stream_in = self.p_audio.open(
                    format=pyaudio.paInt16, channels=self.channels, rate=self.sample_rate,
                    input=True, frames_per_buffer=self.chunk
                )
        except Exception as e:
            logger.warning("Fallo en default mic: %s. Buscando alternativo...", e)
            self.stream_in = self._find_fallback_device(input=True)

        speaker_index_env = os.getenv("SPEAKER_INDEX")
        try:
            if speaker_index_env is not None:
                self.stream_out = self.p_audio.open(
                    format=pyaudio.paInt16, channels=self.channels, rate=24000,
                    output=True, frames_per_buffer=self.chunk, output_device_index=int(speaker_index_env)
                )
                logger.info(f"Usando Altavoz especificado en .env (Index: {speaker_index_env})")
            else:
                self.stream_out = self.p_audio.open(
                    format=pyaudio.paInt16, channels=self.channels, rate=24000,
                    output=True, frames_per_buffer=self.chunk
                )
        except Exception as e:
            logger.warning("Fallo en default altavoz: %s. Buscando alternativo...", e)
            self.stream_out = self._find_fallback_device(input=False)
            
        logger.info("Tarjetas de Hardware instanciadas. Frames Chunk: %d", self.chunk)

    def _find_fallback_device(self, input=True):
        rate = self.sample_rate if input else 24000
        for i in range(self.p_audio.get_device_count()):
            try:
                dev = self.p_audio.get_device_info_by_index(i)
                if input and dev['maxInputChannels'] > 0:
                    stream = self.p_audio.open(
                        format=pyaudio.paInt16, channels=self.channels, rate=rate,
                        input=True, frames_per_buffer=self.chunk, input_device_index=i
                    )
                    logger.info("Seleccionado Micrófono Alternativo: %s", dev['name'])
                    return stream
                elif not input and dev['maxOutputChannels'] > 0:
                    stream = self.p_audio.open(
                        format=pyaudio.paInt16, channels=self.channels, rate=rate,
                        output=True, frames_per_buffer=self.chunk, output_device_index=i
                    )
                    logger.info("Seleccionado Altavoz Alternativo: %s", dev['name'])
                    return stream
            except Exception:
                continue
        raise RuntimeError("No se encontraron dispositivos de audio compatibles con 16Khz.")

    async def read_chunk(self):
        """Lectura liberada a un ThreadPool Asíncrono"""
        # Ejecuta la lectura bloqueante aislando a Gemini
        return await asyncio.to_thread(self.stream_in.read, self.chunk, False)

    async def write_chunk(self, data):
        """Escritura liberada a un ThreadPool Asíncrono"""
        await asyncio.to_thread(self.stream_out.write, data)

    def close(self):
        if self.is_running:
            self.is_running = False
            self.stream_in.stop_stream()
            self.stream_in.close()
            self.stream_out.stop_stream()
            self.stream_out.close()
            self.p_audio.terminate()
            logger.info("Controladores de sonido apagados limpiamente.")
