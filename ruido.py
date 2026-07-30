import subprocess
import os
import sys

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
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

def iniciar_ruido_background():
    if not os.path.exists(AUDIO_PATH):
        raise FileNotFoundError(f"No se encontró el archivo de audio en: {AUDIO_PATH}")
    return subprocess.Popen(obtener_cmd(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    if not os.path.exists(AUDIO_PATH):
        print(f"Error: No se encontró el archivo de audio en: {AUDIO_PATH}")
        sys.exit(1)
    print(f"Iniciando ruido de fondo manual: {AUDIO_PATH} (Volumen: 3%, Loop infinito)...")
    try:
        subprocess.run(obtener_cmd())
    except KeyboardInterrupt:
        print("\nReproducción detenida.")
