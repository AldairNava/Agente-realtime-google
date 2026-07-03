import pyaudio

def listar_dispositivos_audio():
    p = pyaudio.PyAudio()
    
    print("\n" + "="*60)
    print("   DISPOSITIVOS DE AUDIO DETECTADOS (ENTRADAS Y SALIDAS)")
    print("="*60)
    
    # Obtener el número total de dispositivos en el sistema
    num_devices = p.get_device_count()
    
    entradas = []
    salidas = []

    for i in range(num_devices):
        try:
            device_info = p.get_device_info_by_index(i)
            name = device_info.get('name')
            max_input_channels = device_info.get('maxInputChannels')
            max_output_channels = device_info.get('maxOutputChannels')
            sample_rate = int(device_info.get('defaultSampleRate'))

            info_str = f"Índice [{i}]: {name} (Rate: {sample_rate}Hz)"

            # Clasificar si es entrada, salida o ambos
            if max_input_channels > 0:
                entradas.append(info_str)
            if max_output_channels > 0:
                salidas.append(info_str)
                
        except Exception as e:
            print(f"Error leyendo el dispositivo index {i}: {e}")
            continue

    # Mostrar Entradas
    print("\n🔹 DISPOSITIVOS DE ENTRADA (Micrófonos / Captura):")
    if entradas:
        for entrada in entradas:
            print(f"  {entrada}")
    else:
        print("  Ninguno detectado.")

    # Mostrar Salidas
    print("\n🔸 DISPOSITIVOS DE SALIDA (Bocinas / Audífonos):")
    if salidas:
        for salida in salidas:
            print(f"  {salida}")
    else:
        print("  Ninguno detectado.")
        
    print("="*60 + "\n")
    
    # Cerrar el flujo de PyAudio de forma segura
    p.terminate()

if __name__ == "__main__":
    listar_dispositivos_audio()