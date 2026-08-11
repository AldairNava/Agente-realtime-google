import os
import sys
import glob

# Importar la funcion original
from wav_to_mp3 import convertir_wav_a_mp3

def limpiar_recordings():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    
    if not os.path.exists(assets_dir):
        print(f"La carpeta no existe: {assets_dir}")
        return
        
    # Buscar en todas las subcarpetas assets/*/llamadas_grabadas/*.wav
    wav_files = glob.glob(os.path.join(assets_dir, "*", "llamadas_grabadas", "*.wav"))
    
    if not wav_files:
        print("No se encontraron archivos .wav en las carpetas de llamadas_grabadas.")
        return
        
    print(f"Se encontraron {len(wav_files)} archivos .wav. Procesando...")
    
    for wav_path in wav_files:
        try:
            print("-" * 40)
            convertir_wav_a_mp3(wav_path)
            
            # Ahora wav_to_mp3 guarda el mp3 en la misma carpeta que el wav
            nombre_sin_ext = os.path.splitext(os.path.basename(wav_path))[0]
            carpeta_wav = os.path.dirname(os.path.abspath(wav_path))
            ruta_mp3 = os.path.join(carpeta_wav, f"{nombre_sin_ext}.mp3")
            
            if os.path.exists(ruta_mp3):
                os.remove(wav_path)
                print(f"[EXITO] Archivo .wav original eliminado: {os.path.basename(wav_path)}")
            else:
                print(f"[ERROR] No se pudo verificar la creación del mp3. No se borró el wav.")
        except Exception as e:
            print(f"[ERROR] Ocurrió un error al procesar {os.path.basename(wav_path)}: {e}")
            
    print("-" * 40)
    print("Proceso finalizado.")

if __name__ == "__main__":
    limpiar_recordings()
