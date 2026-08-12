import os
import sys
import ssl
import json
import urllib.request
import zipfile
import io
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("DriverManager")

def get_chrome_version():
    """Obtiene la versión de Google Chrome instalada en Windows usando PowerShell."""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                cmd = f'powershell -Command "(Get-Item \'{path}\').VersionInfo.ProductVersion"'
                version = subprocess.check_output(cmd, shell=True).decode().strip()
                if version:
                    logger.info(f"Detectada versión de Chrome instalada: {version}")
                    return version
            except Exception as e:
                logger.debug(f"Error obteniendo versión de {path}: {e}")
    
    # Intento por Registro
    try:
        import winreg
        for hkey in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for subkey in (
                r"Software\Google\Chrome\BLBeacon",
                r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome"
            ):
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    val_names = ["version", "DisplayVersion"]
                    for val_name in val_names:
                        try:
                            version, _ = winreg.QueryValueEx(key, val_name)
                            if version:
                                logger.info(f"Detectada versión de Chrome desde registro: {version}")
                                return version
                        except FileNotFoundError:
                            continue
                except Exception:
                    continue
    except Exception:
        pass
    return None

def download_and_extract(url, target_path):
    """Descarga un archivo ZIP desde la URL (omitiendo SSL si es necesario) y extrae chromedriver.exe."""
    logger.info(f"Descargando ChromeDriver desde: {url}")
    ctx = ssl._create_unverified_context()
    
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    with urllib.request.urlopen(req, context=ctx) as response:
        zip_data = response.read()
    
    logger.info("Descarga completada. Extrayendo chromedriver.exe...")
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for file_info in z.infolist():
            if file_info.filename.endswith("chromedriver.exe"):
                # Extraer directamente
                filename = os.path.basename(file_info.filename)
                with z.open(file_info) as source, open(target_path, "wb") as target:
                    target.write(source.read())
                logger.info(f"ChromeDriver extraído en: {target_path}")
                return True
    return False

def get_or_download_chromedriver(project_root=None):
    """
    Busca chromedriver.exe localmente. Si no existe o no es compatible,
    intenta descargarlo automáticamente según la versión instalada de Chrome.
    """
    if project_root is None:
        # Por defecto la raíz es el padre de la carpeta src
        project_root = Path(__file__).parent.parent
    else:
        project_root = Path(project_root)

    chromedriver_path = project_root / "chromedriver.exe"

    # Si ya existe, de momento lo usamos
    if chromedriver_path.exists():
        logger.info(f"ChromeDriver local encontrado en: {chromedriver_path}")
        return str(chromedriver_path.absolute())

    # Si no existe, intentamos autodescargarlo
    chrome_version = get_chrome_version()
    if not chrome_version:
        logger.warning("No se pudo detectar la versión de Chrome. Se usará Selenium Manager.")
        return None

    # Intentar descargar para la versión exacta de Chrome
    url_exact = f"https://storage.googleapis.com/chrome-for-testing-public/{chrome_version}/win64/chromedriver-win64.zip"
    try:
        if download_and_extract(url_exact, chromedriver_path):
            return str(chromedriver_path.absolute())
    except Exception as e:
        logger.warning(f"No se pudo descargar directamente con la versión exacta ({chrome_version}): {e}")

    # Si falla, intentar consultar la API de Chrome for Testing para obtener el patch más cercano
    try:
        ctx = ssl._create_unverified_context()
        api_url = "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json"
        logger.info("Buscando parche compatible en la API de Chrome for Testing...")
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode())
        
        version_parts = chrome_version.split(".")
        if len(version_parts) >= 3:
            build_prefix = ".".join(version_parts[:3])
            build_info = data.get("builds", {}).get(build_prefix)
            if build_info:
                drivers = build_info.get("downloads", {}).get("chromedriver", [])
                for d in drivers:
                    if d.get("platform") == "win64":
                        url = d.get("url")
                        if download_and_extract(url, chromedriver_path):
                            return str(chromedriver_path.absolute())
    except Exception as e:
        logger.warning(f"Error consultando la lista de parches de Chrome for Testing: {e}")

    # Último intento: Buscar el último stable general de Chrome for Testing
    try:
        ctx = ssl._create_unverified_context()
        api_url = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
        logger.info("Intentando descargar el último ChromeDriver estable...")
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, context=ctx) as response:
            data = json.loads(response.read().decode())
        
        stable_info = data.get("channels", {}).get("Stable", {})
        drivers = stable_info.get("downloads", {}).get("chromedriver", [])
        for d in drivers:
            if d.get("platform") == "win64":
                url = d.get("url")
                if download_and_extract(url, chromedriver_path):
                    return str(chromedriver_path.absolute())
    except Exception as e:
        logger.warning(f"Error al descargar último driver estable: {e}")

    logger.error("❌ No se pudo descargar automáticamente el ChromeDriver. Se intentará usar Selenium Manager por defecto.")
    return None


def crear_chrome_driver(chrome_options):
    """
    Inicia Chrome utilizando Selenium Manager (nativo de Selenium 4+).
    Selenium Manager detecta la versión instalada de Chrome y gestiona automáticamente el driver compatible.
    """
    from selenium import webdriver

    logger.info("🌐 Iniciando Chrome con Selenium Manager nativo...")
    return webdriver.Chrome(options=chrome_options)


