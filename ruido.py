import subprocess
import os
import sys
from dotenv import load_dotenv
import pyaudio

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Cargar variables de entorno del archivo .env
load_dotenv(os.path.join(_CURRENT_DIR, ".env"))

AUDIO_PATH = os.path.join(_CURRENT_DIR, "ruido_fondo.m4a")
FFPLAY_PATH = r"C:\ffmpeg\bin\ffplay.exe"

def obtener_cmd():
    exe = FFPLAY_PATH if os.path.exists(FFPLAY_PATH) else "ffplay"
    return [
        exe,
        "-nodisp",
        "-autoexit",
        "-loop", "0",
        "-af", "volume=0.07",
        AUDIO_PATH
    ]

def obtener_nombre_dispositivo(index: int) -> str:
    """Utiliza PyAudio para resolver el nombre oficial de la tarjeta de sonido por su índice."""
    p = pyaudio.PyAudio()
    try:
        info = p.get_device_info_by_index(index)
        name = info.get("name")
        return name
    except Exception as e:
        print(f"Advertencia: No se pudo obtener el nombre del dispositivo index {index}: {e}")
        return None
    finally:
        p.terminate()

def iniciar_ruido_background():
    if not os.path.exists(AUDIO_PATH):
        raise FileNotFoundError(f"No se encontró el archivo de audio en: {AUDIO_PATH}")
    
    env = os.environ.copy()
    speaker_index_str = os.getenv("SPEAKER_INDEX")
    if speaker_index_str is not None:
        try:
            idx = int(speaker_index_str)
            device_name = obtener_nombre_dispositivo(idx)
            if device_name:
                # ffplay utiliza la variable de entorno SDL_AUDIO_DEVICE_NAME para seleccionar la salida
                env["SDL_AUDIO_DEVICE_NAME"] = device_name
        except Exception as e:
            print(f"No se pudo configurar dispositivo específico para ffplay: {e}")
            
    return subprocess.Popen(
        obtener_cmd(), 
        stdout=subprocess.DEVNULL, 
        stderr=subprocess.DEVNULL,
        env=env
    )

if __name__ == "__main__":
    if not os.path.exists(AUDIO_PATH):
        print(f"Error: No se encontró el archivo de audio en: {AUDIO_PATH}")
        sys.exit(1)
        
    env = os.environ.copy()
    speaker_index_str = os.getenv("SPEAKER_INDEX")
    if speaker_index_str is not None:
        try:
            idx = int(speaker_index_str)
            device_name = obtener_nombre_dispositivo(idx)
            if device_name:
                print(f"Redirigiendo ruido de fondo a altavoz: {device_name} (Index: {idx})")
                env["SDL_AUDIO_DEVICE_NAME"] = device_name
        except Exception as e:
            print(f"Error configurando dispositivo: {e}")
            
    print(f"Iniciando ruido de fondo manual: {AUDIO_PATH} (Volumen: 3%, Loop infinito)...")
    try:
        subprocess.run(obtener_cmd(), env=env)
    except KeyboardInterrupt:
        print("\nReproducción detenida.")
