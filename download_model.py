import os
import urllib.request
import sys

def download_silero():
    target_dir = os.path.join("src", "resources")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "silero_vad.jit")
    
    url = "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.jit"
    print(f"Descargando Silero VAD desde {url}...")
    try:
        urllib.request.urlretrieve(url, target_path)
        print(f"¡Éxito! El modelo se ha guardado en: {target_path}")
    except Exception as e:
        print(f"Error descargando el modelo: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_silero()
