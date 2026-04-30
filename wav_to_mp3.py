"""
Conversor WAV -> MP3
Uso: python wav_to_mp3.py <ruta_al_archivo.wav>
El MP3 resultante se guarda en: recordings/mp3/
"""

import sys
import os

def convertir_wav_a_mp3(ruta_wav: str):
    # Validar que se recibió un archivo WAV
    if not os.path.isfile(ruta_wav):
        print(f"[ERROR] No se encontró el archivo: {ruta_wav}")
        sys.exit(1)

    if not ruta_wav.lower().endswith(".wav"):
        print(f"[ERROR] El archivo no es un WAV: {ruta_wav}")
        sys.exit(1)

    try:
        from pydub import AudioSegment
    except ImportError:
        print("[ERROR] Falta la librería 'pydub'. Instálala con:")
        print("        pip install pydub")
        print("        También necesitas ffmpeg instalado en el sistema.")
        sys.exit(1)

    # Carpeta de salida: recordings/mp3/ relativa a este script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    carpeta_mp3 = os.path.join(base_dir, "recordings", "mp3")
    os.makedirs(carpeta_mp3, exist_ok=True)

    # Nombre del archivo de salida
    nombre_sin_ext = os.path.splitext(os.path.basename(ruta_wav))[0]
    ruta_mp3 = os.path.join(carpeta_mp3, f"{nombre_sin_ext}.mp3")

    print(f"[INFO] Convirtiendo: {ruta_wav}")
    audio = AudioSegment.from_wav(ruta_wav)
    audio.export(ruta_mp3, format="mp3", bitrate="192k")
    print(f"[OK]   MP3 guardado en: {ruta_mp3}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python wav_to_mp3.py <ruta_al_archivo.wav>")
        print("     No se pasó ningún archivo. El script no hace nada.")
        sys.exit(0)

    ruta_entrada = sys.argv[1].strip('"').strip("'")
    convertir_wav_a_mp3(ruta_entrada)
