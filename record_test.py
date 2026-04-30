import pyaudio
import wave
import os

CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
RECORD_SECONDS = 4
WAVE_OUTPUT_FILENAME = "audio_grabado.wav"

p = pyaudio.PyAudio()

mic_index = os.getenv("MICROPHONE_INDEX")
device_index = int(mic_index) if mic_index is not None else None

print(f"==================================================")
print(f" GRABADORA DE DIAGNÓSTICO (Microfono: {device_index if device_index else 'Default'})")
print(f"==================================================")
print("¡Habla ahora! Grabando 4 segundos exactos...")

try:
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK,
                    input_device_index=device_index)

    frames = []
    # (RATE / CHUNK) * Segundos
    for i in range(0, int((RATE / CHUNK) * RECORD_SECONDS)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("Grabación finalizada. Guardando y cerrando...")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

    print(f"\n[ÉXITO] Archivo creado: {WAVE_OUTPUT_FILENAME}")
    print(f"-> Ve a la carpeta de tu proyecto y reproduce el archivo '{WAVE_OUTPUT_FILENAME}' con tu reproductor de Windows.")

except Exception as e:
    print(f"Error al grabar: {e}")
