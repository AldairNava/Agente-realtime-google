import asyncio
import os
import sys
from dotenv import load_dotenv

# Importamos los subsistemas sin mocks para ejecución real
from audio_interfaces.local_audio import LocalAudioInterface
from vad_processor import VADProcessor
from agent_core import VoiceAgent

load_dotenv()

async def run_real_integration_test():
    """
    Realiza una prueba integral (Integration Test), inicializando
    el hardware de la máquina, validando red y descargando modelos IA
    para garantizar que nada falle en producción.
    """
    print("=====================================================")
    print(" INICIANDO PRUEBA REAL (QA HARDWARE E INTEGRACIÓN) ")
    print("=====================================================")
    
    print("[1/4] Verificando Sistema de Entorno y Claves...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "tu_clave_de_api_aqui":
        print("❌ FALLO CRÍTICO: No se encontró 'GEMINI_API_KEY' válida en tu archivo .env")
        sys.exit(1)
    else:
        print("✅ Clave de cifrado inicial cargada.")

    print("\n[2/4] Aprovisionando Tarjetas de Sonido (Hardware PyAudio)...")
    try:
        # Esto prenderá el micrófono físicamente y abrirá la tarjeta de sonido
        audio = LocalAudioInterface(chunk=512)
        if not audio.is_running:
            raise Exception("Estado de tarjeta caído tras inicialización.")
            
        print("   - Ejecutando intento real de lectura (Micrófono)...")
        test_chunk = await audio.read_chunk()
        
        print("   - Ejecutando intento real de escritura (Altavoces)...")
        await audio.write_chunk(b'\x00' * len(test_chunk)) # Reproduce estática silenciosa de validación
        
        audio.close()
        print("✅ Hardware R/W (Lectura y Escritura Full-Duplex) validado localmente.")
    except Exception as e:
        print(f"❌ FALLO en Tarjetas de Audio Físicas: {e}")
        print("   -> Sugerencia: Revisa los permisos de tu sistema, o si otro programa usa el micro.")
        sys.exit(1)

    print("\n[3/4] Inicializando Cerebro VAD (Silero Neuronal - PyTorch)...")
    print("      (Nota: Si es la primera vez, verás cómo se descarga de Internet al caché)")
    try:
        vad = VADProcessor()
        
        # Le enviamos un bloque absoluto de ceros (Silencio de Radio) para ver su reacción.
        silence = b'\x00' * 1024
        is_speech = vad.is_speech(silence)
        
        if is_speech:
             print("⚠️ ADVERTENCIA CURIOSA: La Red detectó un 'fantasma' en bloque silenciado (falso positivo).")
        print("✅ Inferencia VAD Exitosa. Tarjeta CPU corriendo tensores de PyTorch sin colapsar.")
    except Exception as e:
        print(f"❌ FALLO en Neuronas de Detección de Voz: {e}")
        sys.exit(1)

    print("\n[4/4] Ensamblando Núcleo General (Gemini Voice Agent)...")
    try:
        agent = VoiceAgent(api_key=api_key)
        print("✅ Compilador IA Principal conectado.")
    except Exception as e:
        print(f"❌ FALLO en Orquestador Core: {e}")
        sys.exit(1)

    print("\n=====================================================")
    print(" 🏆 TODO EXCELENTE: Tu máquina e infraestructura están perfectas. ")
    print(" Puedes empezar el turno iniciando el programa principal:")
    print("   > python main.py")
    print("=====================================================")

if __name__ == "__main__":
    # Suprime el event loop exception visual en tests cortos si es que Windows se queja de IO Proactor
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(run_real_integration_test())
