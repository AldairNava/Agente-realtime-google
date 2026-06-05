import os
import sys
import time
import json
import logging
import argparse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options

# Configuración de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - SiebelRetencionRPA - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SiebelRetencionRPA")

# Directorios del proyecto
_SCRIPT_DIR = Path(__file__).parent.parent
sys.path.append(str(_SCRIPT_DIR))
SIGNALS_DIR = _SCRIPT_DIR / "assets" / "retencion" / "rpa_signals"

# Credenciales y URL de Siebel
SIEBLE = 'https://crm.izzi.mx/siebel/app/ecommunications/esn'
user = 'p-efgarciac'
password = 'Rpa$CyberBack01'

# XPaths de Inicio de Sesión
xpath_usuario_login = '/html/body/form/div/div[2]/div[1]/span/input'
xpath_password_login = '/html/body/form/div/div[2]/div[2]/span/input'
xpath_boton_login = '/html/body/form/div/div[2]/div[4]/a'
xpath_paginaInicial_menu = '/html/body/div[1]/div/div[3]/div/div/div[1]/div[3]/ul/li[1]/a/span'

# XPaths de Navegación y Consulta
xpath_pantalla_unica = "//a[@title='Pantalla Única de Consulta' or contains(text(), 'Pantalla Única de Consulta')]"
xpath_btn_consulta = "//button[@rn='NewQuery' or @title='Consulta' or contains(span, 'Consulta')]"
xpath_home_tab = "//a[@title='Página inicial' or contains(text(), 'Página inicial')]"

# XPaths de Campos de Entrada
xpath_input_cuenta = "//input[@aria-label='Numero Cuenta' or @un='Numero Cuenta' or @name='s_12_1_163_0']"
xpath_input_telefono = "//input[@aria-label='Teléfonos' or @un='Teléfonos' or @name='s_12_1_3_0']"
xpath_input_nombre = "//input[@aria-label='Nombre Cuenta' or @un='Nombre Cuenta' or @name='s_12_1_75_0']"


def bucleEncuentraItems(driver, xpath):
    contador = 0
    while True:
        try:
            if contador >= 20:
                logger.warning(f"No se encontró el elemento: {xpath}")
                return None
            return driver.find_element(By.XPATH, xpath)
        except Exception:
            contador += 1
            time.sleep(0.5)


def bucleEncuentraItemsClick(driver, xpath):
    contador = 0
    while True:
        try:
            if contador >= 20:
                logger.warning(f"No se pudo dar clic al elemento: {xpath}")
                return False
            el = driver.find_element(By.XPATH, xpath)
            time.sleep(0.5)
            el.click()
            time.sleep(0.5)
            return True
        except Exception:
            contador += 1
            time.sleep(0.5)


def bucleEncuentraItemsLong(driver, xpath):
    contador = 0
    while True:
        try:
            if contador >= 60:
                logger.warning(f"No se encontró el elemento (espera larga): {xpath}")
                return None
            return driver.find_element(By.XPATH, xpath)
        except Exception:
            contador += 1
            time.sleep(1)


def iniciarDriver(headless: bool = False):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--audio-output-channels=0")
        chrome_options.add_argument("--disable-features=AudioServiceOutOfProcess")
        chrome_options.set_capability("unhandledPromptBehavior", "accept")

        # Directorio de perfil persistente
        profile_dir = _SCRIPT_DIR / "assets" / "retencion" / "chrome_profile_siebel"
        chrome_options.add_argument(f"--user-data-dir={str(profile_dir.absolute())}")

        perfil_nuevo = not profile_dir.exists()

        if headless and not perfil_nuevo:
            # chrome_options.add_argument("--headless=new")
            print("Headless mode is enabled")

        if perfil_nuevo:
            logger.warning("=" * 80)
            logger.warning("❌ PERFIL DE CHROME NUEVO DETECTADO (SIEBEL)")
            logger.warning("Se abrirá el navegador para que instales la extensión de RPA.")
            logger.warning("Favor de instalar la extensión en la ventana de Chrome que se abrirá.")
            logger.warning("Una vez instalada, cierra el navegador y vuelve a iniciar este RPA.")
            logger.warning("=" * 80)

            logger.info("🌐 Iniciando Chrome visible usando Selenium Manager...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.maximize_window()

            extension_url = "https://chromewebstore.google.com/detail/rpa-extension/ccilojpjnmepojkjkdpohdkbjpkfoojd"
            logger.info(f"📦 Navegando a la Chrome Web Store: {extension_url}")
            driver.get(extension_url)

            try:
                driver.execute_script(
                    "alert('El perfil de Chrome para Siebel es nuevo.\\n\\nPor favor, instala la extensión de RPA en este navegador.\\n\\nUna vez instalada, presiona ENTER en la consola de comandos para finalizar y luego reinicia el RPA.');"
                )
            except Exception:
                pass

            input("\n👉 Presiona ENTER aquí en la consola después de instalar la extensión para finalizar...")

            try:
                driver.quit()
            except Exception:
                pass
            logger.info("👋 Navegador cerrado. Por favor inicia el RPA de nuevo.")
            sys.exit(0)

        # Si el perfil ya existe, iniciar normalmente
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        logger.info("▬ Webdriver abierto correctamente")

        # Inyección de alertas antes de la carga de páginas
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": """
                window._capturedAlerts = [];
                window.alert   = msg => window._capturedAlerts.push(msg);
                window.confirm = ()  => true;
                window.prompt  = ()  => null;
            """}
        )
        return driver
    except Exception as e:
        logger.error(f"Error al iniciar WebDriver: {e}")
        return None


def loginSiebel(headless: bool = False):
    intentos = 0
    max_intentos = 4

    while intentos < max_intentos:
        logger.info(f"Intentando iniciar sesión en Siebel (Intento {intentos+1}/{max_intentos})...")
        driver = iniciarDriver(headless=headless)
        if not driver:
            intentos += 1
            time.sleep(2)
            continue

        try:
            driver.get(SIEBLE)
            time.sleep(4)

            # Verificar si ya estamos logueados de forma persistente
            try:
                menu = driver.find_element(By.XPATH, xpath_paginaInicial_menu)
                if menu:
                    logger.info("✅ Sesión persistente activa detectada. Saltando login.")
                    return driver
            except Exception:
                pass

            if "Siebel" in driver.title or len(driver.find_elements(By.XPATH, xpath_usuario_login)) > 0:
                logger.info("Ingresando credenciales...")
                inputUser = bucleEncuentraItems(driver, xpath_usuario_login)
                if inputUser:
                    inputUser.clear()
                    inputUser.send_keys(user)
                
                inputPassword = bucleEncuentraItems(driver, xpath_password_login)
                if inputPassword:
                    inputPassword.clear()
                    inputPassword.send_keys(password)
                
                bucleEncuentraItemsClick(driver, xpath_boton_login)
                
                # Verificar acceso exitoso
                elementoMenu = bucleEncuentraItemsLong(driver, xpath_paginaInicial_menu)
                if not elementoMenu:
                    logger.warning("No se cargó el menú principal tras el login. Reintentando...")
                    driver.quit()
                    intentos += 1
                    continue
                else:
                    logger.info("✅ Inicio de sesión exitoso.")
                    return driver
            else:
                logger.warning("No se detectó la página de inicio de sesión de Siebel. Reintentando...")
                driver.quit()
                intentos += 1
                time.sleep(2)
        except Exception as e:
            logger.error(f"Excepción durante login: {e}")
            try:
                driver.quit()
            except Exception:
                pass
            intentos += 1
            time.sleep(2)

    logger.error("❌ No se pudo ingresar a Siebel tras 4 intentos.")
    return None


def extraer_datos_cliente(driver) -> dict:
    """
    Escanea la pantalla actual en busca de inputs y campos de datos
    para generar un diccionario estructurado del cliente consultado.
    """
    logger.info("🔍 Escaneando datos del cliente en pantalla...")
    datos = {}
    
    for tag in ["input", "textarea"]:
        elements = driver.find_elements(By.TAG_NAME, tag)
        for el in elements:
            try:
                if el.is_displayed():
                    label = (
                        el.get_attribute("aria-label") or 
                        el.get_attribute("un") or 
                        el.get_attribute("placeholder") or 
                        el.get_attribute("name")
                    )
                    val = el.get_attribute("value")
                    if label and val:
                        label = label.strip()
                        val = val.strip()
                        if label and val:
                            datos[label] = val
            except Exception:
                pass

    # Mapeo de campos conocidos a llaves consistentes en español e inglés
    mapping = {
        "Numero Cuenta": "cuenta",
        "Nombre Cuenta": "nombre",
        "Teléfonos": "telefono",
        "Estatus": "estatus",
        "Correo Electrónico": "email"
    }
    for k, v in list(datos.items()):
        for match_key, standard_key in mapping.items():
            if match_key.lower() in k.lower() and standard_key not in datos:
                datos[standard_key] = v

    logger.info(f"✅ Datos obtenidos: {len(datos)} campos mapeados.")
    return datos


def main_loop(driver):
    # Seguimiento en memoria del último elemento buscado
    last_query = {
        "cuenta": None,
        "tel": None,
        "nombre": None
    }
    
    SIGNALS_DIR.mkdir(exist_ok=True)
    logger.info("👀 Vigilando señales en rpa_signals/ ...")
    
    # Comenzar directamente en Pantalla Única de Consulta
    logger.info("🔄 Inicializando en Pantalla Única de Consulta...")
    menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
    if menu_tab:
        driver.execute_script("arguments[0].click();", menu_tab)
    time.sleep(5)
    
    while True:
        try:
            # 1. Definir rutas físicas de señales
            cuenta_file = SIGNALS_DIR / "cuenta.txt"
            tel_file = SIGNALS_DIR / "tel.txt"
            nombre_file = SIGNALS_DIR / "nombre.txt"
            
            # Leer valores si existen
            cuenta_val = cuenta_file.read_text(encoding="utf-8").strip() if cuenta_file.exists() else None
            tel_val = tel_file.read_text(encoding="utf-8").strip() if tel_file.exists() else None
            nombre_val = nombre_file.read_text(encoding="utf-8").strip() if nombre_file.exists() else None
            
            # Limpiar memoria de consulta si el archivo físico fue eliminado por la campaña
            if not cuenta_val:
                last_query["cuenta"] = None
            if not tel_val:
                last_query["tel"] = None
            if not nombre_val:
                last_query["nombre"] = None
                
            hay_nueva_busqueda = False
            
            # 2. Evaluar prioridad de señales nuevas
            if cuenta_val and cuenta_val != last_query["cuenta"]:
                logger.info(f"🎯 Nueva señal de CUENTA detectada: {cuenta_val}")
                hay_nueva_busqueda = True
                
                # Clic en Consulta (Lupa)
                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_cuenta)
                if inp:
                    inp.clear()
                    inp.send_keys(cuenta_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info("🚀 Consulta de Cuenta enviada.")
                    
                    last_query["cuenta"] = cuenta_val
                    last_query["tel"] = None
                    last_query["nombre"] = None
                else:
                    logger.error("No se localizó el campo de entrada de Cuenta.")
                    
            elif tel_val and tel_val != last_query["tel"]:
                logger.info(f"🎯 Nueva señal de TELÉFONO detectada: {tel_val}")
                hay_nueva_busqueda = True
                
                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_telefono)
                if inp:
                    inp.click()  # Habilitación visual de campo en Siebel
                    time.sleep(0.5)
                    inp.clear()
                    inp.send_keys(tel_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info("🚀 Consulta de Teléfono enviada.")
                    
                    last_query["tel"] = tel_val
                    last_query["cuenta"] = None
                    last_query["nombre"] = None
                else:
                    logger.error("No se localizó el campo de entrada de Teléfonos.")
                    
            elif nombre_val and nombre_val != last_query["nombre"]:
                logger.info(f"🎯 Nueva señal de NOMBRE detectada: {nombre_val}")
                hay_nueva_busqueda = True
                
                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_nombre)
                if inp:
                    inp.clear()
                    inp.send_keys(nombre_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info("🚀 Consulta de Nombre enviada.")
                    
                    last_query["nombre"] = nombre_val
                    last_query["cuenta"] = None
                    last_query["tel"] = None
                else:
                    logger.error("No se localizó el campo de entrada de Nombre Cuenta.")
            
            # 3. Extraer información del cliente si realizamos búsqueda
            if hay_nueva_busqueda:
                logger.info("⏳ Esperando respuesta del servidor de Siebel (5s)...")
                time.sleep(5)
                
                datos = extraer_datos_cliente(driver)
                
                datos_path = SIGNALS_DIR / "datos_cliente.json"
                try:
                    datos_path.write_text(json.dumps(datos, ensure_ascii=False, indent=4), encoding="utf-8")
                    logger.info(f"💾 Archivo de datos generado: {datos_path}")
                except Exception as e:
                    logger.error(f"Error escribiendo datos_cliente.json: {e}")
                    
                time.sleep(2)
                
            else:
                # 4. Alternancia a Página Inicial si no hay consultas activas
                logger.info("💤 Sin novedades. Alternando a Página inicial...")
                home_tab = bucleEncuentraItemsLong(driver, xpath_home_tab)
                if home_tab:
                    driver.execute_script("arguments[0].click();", home_tab)
                    logger.info("🏠 Pestaña Página inicial activa. Esperando 5 segundos...")
                    time.sleep(5)
                    
                    # Regresar a consulta para la siguiente validación
                    logger.info("🔄 Regresando a Pantalla Única de Consulta...")
                    menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                    if menu_tab:
                        driver.execute_script("arguments[0].click();", menu_tab)
                    time.sleep(5)
                else:
                    logger.warning("No se encontró la pestaña Página inicial. Esperando en consulta...")
                    time.sleep(5)
                    
        except KeyboardInterrupt:
            logger.info("Ejecución detenida por consola.")
            break
        except Exception as e:
            logger.error(f"Error en la ejecución del ciclo: {e}")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Siebel Retention RPA Client")
    parser.add_argument("--test", action="store_true", help="Ejecutar con el navegador visible (no headless)")
    parser.add_argument("--headless", action="store_true", help="Ejecutar en segundo plano (headless)")
    args = parser.parse_args()
    
    # Headless por defecto a menos que se defina --test
    headless = args.headless or (not args.test)
    
    driver = loginSiebel(headless=headless)
    if not driver:
        sys.exit(1)
        
    try:
        main_loop(driver)
    finally:
        logger.info("Cerrando navegador...")
        try:
            driver.quit()
        except Exception:
            pass
        logger.info("RPA apagado.")


if __name__ == "__main__":
    main()
