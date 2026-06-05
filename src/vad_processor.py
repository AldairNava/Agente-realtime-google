import torch
import numpy as np
import logging
import os
import ssl

# Desactivar la verificación SSL de Python para evitar fallos de conexión al descargar de torch.hub en Windows
ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger(__name__)

class VADProcessor:
    """
    Especialista de Audio:
    Filtro de Ruido basado en Redes Neuronales Profundas (Silero VAD PyTorch).
    """
    def __init__(self, sample_rate=16000, threshold=0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        
        # Obtener ruta absoluta del modelo local
        local_model_path = os.path.join(os.path.dirname(__file__), "resources", "silero_vad.jit")
        
        try:
            if os.path.exists(local_model_path):
                logger.info(f"Cargando Silero VAD localmente desde: {local_model_path}")
                self.model = torch.jit.load(local_model_path)
            else:
                logger.warning(f"Modelo local no encontrado en {local_model_path}. Intentando descargar vía torch.hub...")
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
