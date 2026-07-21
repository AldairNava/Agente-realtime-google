import os
import urllib.request
import sys
import zipfile

def download_silero():
    target_dir = os.path.join(os.path.dirname(__file__), "src", "resources")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "silero_vad.jit")
    
    if os.path.exists(target_path):
        print(f"✅ El modelo Silero VAD ya existe en: {target_path}")
        return True

    urls = [
        "https://raw.githubusercontent.com/snakers4/silero-vad/v4.0/files/silero_vad.jit",
        "https://github.com/snakers4/silero-vad/raw/v4.0/files/silero_vad.jit",
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.jit",
        "https://raw.githubusercontent.com/snakers4/silero-vad/main/src/silero_vad/data/silero_vad.jit",
        "https://raw.githubusercontent.com/snakers4/silero-vad/main/files/silero_vad.jit",
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/files/silero_vad.jit"
    ]
    
    for url in urls:
        print(f"Descargando Silero VAD desde {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response, open(target_path, 'wb') as out_file:
                out_file.write(response.read())
            print(f"¡Éxito! El modelo se ha guardado en: {target_path}")
            return True
        except Exception as e:
            print(f"No se pudo descargar de {url}: {e}")
            
    print("❌ No se pudo descargar el modelo directamente por URL.")
    return False

if __name__ == "__main__":
    download_silero()

