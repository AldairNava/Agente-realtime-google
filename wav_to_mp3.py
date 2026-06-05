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

    # Carpeta de salida: recordings/mp3/ relativa a este script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    carpeta_mp3 = os.path.join(base_dir, "recordings", "mp3")
    os.makedirs(carpeta_mp3, exist_ok=True)

    # Nombre del archivo de salida
    nombre_sin_ext = os.path.splitext(os.path.basename(ruta_wav))[0]
    ruta_mp3 = os.path.join(carpeta_mp3, f"{nombre_sin_ext}.mp3")

    print(f"[INFO] Convirtiendo: {ruta_wav}")

    # Método 1: Intentar usar lameenc (no requiere ffmpeg)
    try:
        import lameenc
        import wave
        
        with wave.open(ruta_wav, 'rb') as wav_file:
            channels = wav_file.getnchannels()
            rate = wav_file.getframerate()
            sampwidth = wav_file.getsampwidth()
            
            if sampwidth != 2:
                raise ValueError("Solo se soportan archivos WAV PCM de 16 bits.")
            
            encoder = lameenc.Encoder()
            encoder.set_channels(channels)
            encoder.set_in_sample_rate(rate)
            encoder.set_bit_rate(192)
            
            with open(ruta_mp3, 'wb') as mp3_file:
                pcm_data = wav_file.readframes(wav_file.getnframes())
                mp3_data = encoder.encode(pcm_data)
                mp3_file.write(mp3_data)
                mp3_file.write(encoder.flush())
        
        print(f"[OK]   MP3 guardado en (vía lameenc): {ruta_mp3}")
        return
        
    except ImportError:
        pass
    except Exception as e:
        print(f"[WARNING] Error usando lameenc: {e}. Intentando fallback...")

    # Método 2: Fallback a pydub (requiere ffmpeg)
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_wav(ruta_wav)
        audio.export(ruta_mp3, format="mp3", bitrate="192k")
        print(f"[OK]   MP3 guardado en (vía pydub): {ruta_mp3}")
    except ImportError:
        print("[ERROR] No se pudo convertir. Instala 'lameenc' o 'pydub' + 'ffmpeg'.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error al exportar con pydub (¿tienes ffmpeg instalado?): {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python wav_to_mp3.py <ruta_al_archivo.wav>")
        print("     No se pasó ningún archivo. El script no hace nada.")
        sys.exit(0)

    ruta_entrada = sys.argv[1].strip('"').strip("'")
    convertir_wav_a_mp3(ruta_entrada)
