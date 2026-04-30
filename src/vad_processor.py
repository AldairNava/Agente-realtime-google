import torch
import numpy as np
import logging

logger = logging.getLogger(__name__)

class VADProcessor:
    """
    Especialista de Audio:
    Filtro de Ruido basado en Redes Neuronales Profundas (Silero VAD PyTorch).
    """
    def __init__(self, sample_rate=16000, threshold=0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        logger.info("Cargando modelo neuronal Silero VAD (Descargará ONNX la primera vez)...")
        try:
            # Estado del Arte: Ignora teclados y ruido de fondo de Call Center
            self.model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            # Eval mode desactiva gradients = máxima velocidad de Inferencia In-Memory
            self.model.eval()
            self.model.to('cpu')
            logger.info("Silero VAD inicializado en la CPU.")
        except Exception as e:
            logger.error(f"Fallo crítico cargando Silero VAD: {e}")
            raise

    def is_speech(self, audio_chunk: bytes) -> bool:
        """ Evalúa si el binario de audio contiene voz filtrando ruido. """
        try:
            if len(audio_chunk) == 0: return False
            
            # Silero lee float32 (arrays n-dimensionales). Pyaudio da pcm16 int.
            audio_np = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_np)
            
            if audio_tensor.numel() > 0:
                # Retorna la probalidad cruda de que haya voz en ese fragmento de 32ms
                speech_prob = self.model(audio_tensor, self.sample_rate).item()
                return speech_prob > self.threshold
                
            return False
        except Exception as e:
            # Prevenir que la red se caiga silenciando y loggeando errores de tensores
            logger.warning(f"[VAD] Fallo en inferencia veloz: {e}")
            return False
