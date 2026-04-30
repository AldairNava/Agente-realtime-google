import pyaudio
import math
import struct
import time
import os

CHUNK = 512
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

p = pyaudio.PyAudio()

print("==============================================")
print("     BÚSQUEDA AUTOMÁTICA DE MICRÓFONO")
print("==============================================")
print("Voy a probar TODOS los micrófonos conectados a tu computadora uno por uno.")
print("*** POR FAVOR, HABLA CONSTANTEMENTE EN VOZ ALTA AHORA MISMO ***")
print("(Ejemplo: Di 'Probando micrófono 1, 2, 3...' sin parar)\n")

time.sleep(2)

valid_mics = []
for i in range(p.get_device_count()):
    try:
        dev = p.get_device_info_by_index(i)
        if dev['maxInputChannels'] > 0:
            print(f"Probando [Index {i}]: {dev['name'][:30]}... ", end="", flush=True)
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=i)
            
            max_rms = 0
            # Graba 1.5 segundos por cada micrófono
            for _ in range(int(RATE / CHUNK * 1.5)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                count = len(data) // 2
                shorts = struct.unpack(f"{count}h", data)
                sum_squares = sum(s**2 for s in shorts)
                rms = math.sqrt(sum_squares / count) if count > 0 else 0
                if rms > max_rms: max_rms = rms
                
            stream.stop_stream()
            stream.close()
            
            if max_rms > 50: # Umbral muy bajo para ser permisivos
                print(f"¡Voz detectada! (Pico RMS: {int(max_rms)})")
                valid_mics.append((i, dev['name'], max_rms))
            else:
                print("Puro silencio.")
    except Exception as e:
        print("Incompatible o no disponible.")

p.terminate()

if not valid_mics:
    print("\n[RESULTADO FATAL] Ningún dispositivo logró escuchar tu voz.")
    print("Revisa: \n1. ¿El micrófono está muteado físicamente? \n2. ¿Windows Configuración -> Privacidad -> Micrófono tiene el acceso bloqueado?")
else:
    valid_mics.sort(key=lambda x: x[2], reverse=True)
    best_mic = valid_mics[0]
    print(f"\n[ÉXITO] El mejor dispositivo es: {best_mic[1]} (ID: {best_mic[0]})")
    
    env_file = ".env"
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    with open(env_file, "w") as f:
        found = False
        for line in lines:
            if line.startswith("MICROPHONE_INDEX="):
                f.write(f"MICROPHONE_INDEX={best_mic[0]}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"\nMICROPHONE_INDEX={best_mic[0]}\n")
            
    print("El archivo '.env' de tu agente ha sido actualizado automáticamente con este Micrófono.")
    print("Ya puedes ejecutar 'python main.py' con normalidad.")
