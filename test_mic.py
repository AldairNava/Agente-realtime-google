import pyaudio
import math
import struct
import time

CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

p = pyaudio.PyAudio()
print("Iniciando escaneo de hardware de audio...")

stream = None
try:
    # Intenta capturar el hardware principal (igual que el Agente)
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print(f"Micrófono Acoplado al default del OS: {p.get_default_input_device_info()['name']}")
except Exception as e:
    print("Fallo en default, buscando fallback...", e)
    for i in range(p.get_device_count()):
        try:
            dev = p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0:
                stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=i)
                print(f"Micrófono Acoplado al Fallback: {dev['name']}")
                break
        except Exception:
            continue

if not stream:
    print("\n[ERROR CRÍTICO] Windows no detecta NINGÚN micrófono compatible en tu computadora.")
    exit(1)

print("\n==================================")
print("  ANALIZADOR ESPECTRAL EN VIVO ")
print("==================================")
print("HABLA AHORA para probar el micrófono (La prueba durará 10 segundos)...\n")

start_time = time.time()
try:
    while time.time() - start_time < 10:
        data = stream.read(CHUNK, exception_on_overflow=False)
        count = len(data) // 2
        shorts = struct.unpack(f"{count}h", data)
        sum_squares = sum(s**2 for s in shorts)
        rms = math.sqrt(sum_squares / count) if count > 0 else 0
        
        # Escala visual
        vol = min(int(rms / 100), 40)
        bar = "#" * vol + "-" * (40 - vol)
        
        # Muestra si detectó Voz o Silencio en base al umbral empírico de RMS
        estado = "VOZ HUMANA DETECTADA" if rms > 150 else "Silencio/Ruido   "
        
        print(f"\r{estado} | Nivel RMS {int(rms):04d} | [{bar}]", end="", flush=True)
        
except KeyboardInterrupt:
    pass
finally:
    print("\n\n=== PRUEBA FINALIZADA ===")
    stream.stop_stream()
    stream.close()
    p.terminate()
