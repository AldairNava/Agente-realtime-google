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
_SCRIPT_DIR = Path(__file__).parent.parent.parent
sys.path.append(str(_SCRIPT_DIR))
SIGNALS_DIR = _SCRIPT_DIR / "assets" / "retencion" / "rpa_signals"

# Credenciales y URL de Siebel
SIEBLE = 'https://crm.izzi.mx/siebel/app/ecommunications/esn'
user = 'p-efgarciac'
password = 'Rpa$CyberBack02'

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

        # Usar chromedriver local si existe
        from selenium.webdriver.chrome.service import Service
        driver_path = _SCRIPT_DIR / "chromedriver.exe"

        if perfil_nuevo:
            logger.warning("=" * 80)
            logger.warning("❌ PERFIL DE CHROME NUEVO DETECTADO (SIEBEL)")
            logger.warning("Se abrirá el navegador para que instales la extensión de RPA.")
            logger.warning("Favor de instalar la extensión en la ventana de Chrome que se abrirá.")
            logger.warning("Una vez instalada, cierra el navegador y vuelve a iniciar este RPA.")
            logger.warning("=" * 80)

            if driver_path.exists():
                logger.info("🌐 Iniciando Chrome usando chromedriver local...")
                service = Service(executable_path=str(driver_path))
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                logger.info("🌐 Iniciando Chrome usando Selenium Manager...")
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
    Escanea exhaustivamente la pantalla actual de Siebel en busca de inputs, selects, textareas,
    etiquetas y celdas de tablas para generar un diccionario estructurado completo del cliente.
    """
    logger.info("🔍 Escaneando datos detallados del cliente en pantalla...")
    import re
    datos = {}
    items_facturacion = []

    def _clean_label(text: str) -> str:
        if not text:
            return ""
        # Eliminar etiquetas HTML como <font color="red">
        clean = re.sub(r'<[^>]+>', '', str(text)).strip()
        # Normalizar espacios
        clean = re.sub(r'\s+', ' ', clean)
        return clean

    # 1. Escanear elementos interactivos (input, textarea, select)
    for tag in ["input", "textarea", "select"]:
        try:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    if el.is_displayed():
                        # Obtener la etiqueta más limpia disponible (priorizando rn en Siebel)
                        raw_label = (
                            el.get_attribute("rn") or 
                            el.get_attribute("aria-label") or 
                            el.get_attribute("un") or 
                            el.get_attribute("placeholder") or 
                            el.get_attribute("name") or ""
                        )
                        label = _clean_label(raw_label)

                        # Si la etiqueta viene vacía, intentar por aria-labelledby
                        if not label:
                            labelledby = el.get_attribute("aria-labelledby")
                            if labelledby:
                                try:
                                    lbl_el = driver.find_element(By.ID, labelledby)
                                    label = _clean_label(lbl_el.text)
                                except Exception:
                                    pass

                        # Obtener el valor del campo
                        val = el.get_attribute("value")
                        if tag == "select" and not val:
                            try:
                                val = el.find_element(By.XPATH, ".//option[@selected]").text
                            except Exception:
                                pass

                        val = _clean_label(val)

                        if label and val:
                            datos[label] = val
                            # Si la etiqueta limpia es diferente de la etiqueta cruda, guardar ambas
                            if raw_label and raw_label != label:
                                datos[_clean_label(raw_label)] = val
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error al escanear tag {tag}: {e}")

    # 2. Escanear celdas de tablas jqGrid en Siebel (Encabezados → Valores)
    try:
        tables = driver.find_elements(By.XPATH, "//table[contains(@class, 'ui-jqgrid-btable') or contains(@class, 'siebui-grid')]")
        for table in tables:
            try:
                headers = [th.text.strip() for th in table.find_elements(By.XPATH, ".//th")]
                rows = table.find_elements(By.XPATH, ".//tr")
                for row in rows:
                    cells = row.find_elements(By.XPATH, ".//td")
                    if cells:
                        cell_texts = [c.text.strip() for c in cells]
                        for idx, text in enumerate(cell_texts):
                            if text:
                                header_name = headers[idx] if idx < len(headers) and headers[idx] else f"col_{idx}"
                                clean_header = _clean_label(header_name)
                                if clean_header and clean_header not in datos:
                                    datos[clean_header] = text
                                
                                # Filtrar productos o ítems de servicios
                                if len(text) > 3 and any(token in text for token in ["izzi", "AXT", "wizz", "UNESCO", "Afizzionados", "Internet", "HD M", "2P", "3P", "TV", "FTTH", "HFC"]):
                                    if text not in items_facturacion:
                                        items_facturacion.append(text)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Advertencia al escanear tablas de Siebel: {e}")

    # 3. Escanear elementos sueltos con clase siebui-value o grid-cell
    try:
        value_spans = driver.find_elements(By.XPATH, "//span[contains(@class, 'siebui-value') or contains(@class, 'grid-cell')]")
        for span in value_spans:
            try:
                text = span.text.strip()
                if text and len(text) > 3:
                    if any(token in text for token in ["izzi", "AXT", "wizz", "UNESCO", "Afizzionados", "Internet", "HD M", "2P", "3P", "TV", "FTTH", "HFC"]):
                        if text not in items_facturacion:
                            items_facturacion.append(text)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Advertencia al escanear celdas de productos sueltas: {e}")

    datos["items_facturacion"] = items_facturacion

    # 4. Mapeo normalizado a llaves estándar para el agente
    mapping = {
        "Numero Cuenta": "cuenta",
        "Nombre Cuenta": "nombre",
        "Teléfonos": "telefono",
        "Estatus": "estatus",
        "Correo Electrónico": "email",
        "Saldo Vencido": "saldo_vencido",
        "Saldo Actual": "saldo_actual",
        "Saldo Total": "saldo_total",
        "Saldo": "saldo"
    }

    for k, v in list(datos.items()):
        clean_k = _clean_label(k)
        for match_key, standard_key in mapping.items():
            if match_key.lower() in clean_k.lower() and standard_key not in datos:
                datos[standard_key] = v

    logger.info(f"✅ Datos obtenidos: {len(datos)} campos mapeados, {len(items_facturacion)} ítems detectados.")
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
            # 0. Revisar si hay un archivo de pollution para Caso de Negocio
            pollution_file = Path(r"C:\pollution\pollution_cte.txt")
            if pollution_file.exists():
                logger.info("🚨 Archivo pollution_cte.txt detectado. Procesando Caso de Negocio...")
                content = pollution_file.read_text(encoding="utf-8").strip()
                try:
                    pollution_file.unlink() # Eliminar inmediatamente para evitar bucles
                except Exception as e:
                    logger.error(f"Error borrando pollution_cte.txt: {e}")
                
                parts = content.split("|")
                if len(parts) >= 2:
                    p_cuenta = parts[0].strip()
                    p_tipo = parts[1].strip()
                    
                    # 0) Resetear estado: regresar siempre al menú/pantalla principal antes de procesar pollution
                    logger.info("🏠 Reseteando estado: Regresando a Página inicial antes de procesar Caso de Negocio...")
                    home_tab = bucleEncuentraItemsLong(driver, xpath_home_tab)
                    if home_tab:
                        driver.execute_script("arguments[0].click();", home_tab)
                        time.sleep(3)
                        menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                        if menu_tab:
                            driver.execute_script("arguments[0].click();", menu_tab)
                        time.sleep(3)

                    # 1) Buscar la cuenta en Siebel
                    bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                    time.sleep(1)
                    inp = bucleEncuentraItems(driver, xpath_input_cuenta)
                    if inp:
                        inp.clear()
                        inp.send_keys(p_cuenta)
                        inp.send_keys(Keys.RETURN)
                        logger.info(f"🚀 Consulta de Cuenta ({p_cuenta}) para Caso de Negocio ({p_tipo}) enviada.")
                        time.sleep(5)
                        
                        # 2) Llenar y cerrar CN
                        try:
                            from tools.siebel_casos_negocio import llenar_y_cerrar_CN
                            exito = llenar_y_cerrar_CN(driver, p_tipo)
                            if not exito:
                                logger.error("No se pudo generar/cerrar el Caso de Negocio.")
                        except Exception as e:
                            logger.error(f"Error ejecutando llenar_y_cerrar_CN: {e}")
                        
                        # 3) Regresar a Home y Consulta para resetear el estado
                        home_tab = bucleEncuentraItemsLong(driver, xpath_home_tab)
                        if home_tab:
                            driver.execute_script("arguments[0].click();", home_tab)
                            time.sleep(3)
                            menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                            if menu_tab:
                                driver.execute_script("arguments[0].click();", menu_tab)
                            time.sleep(3)
                        continue # Salta a la siguiente iteración del while
                else:
                    logger.error(f"Formato inválido en pollution_cte.txt: {content}")

            # 1. Definir rutas físicas de señales normales (revisar en rpa_signals/ y en la raíz del proyecto)
            cuenta_file = SIGNALS_DIR / "cuenta.txt"
            if not cuenta_file.exists() and (_SCRIPT_DIR / "cuenta.txt").exists():
                cuenta_file = _SCRIPT_DIR / "cuenta.txt"

            tel_file = SIGNALS_DIR / "tel.txt"
            if not tel_file.exists() and (_SCRIPT_DIR / "tel.txt").exists():
                tel_file = _SCRIPT_DIR / "tel.txt"

            nombre_file = SIGNALS_DIR / "nombre.txt"
            if not nombre_file.exists() and (_SCRIPT_DIR / "nombre.txt").exists():
                nombre_file = _SCRIPT_DIR / "nombre.txt"
            
            # Leer valores si existen
            cuenta_val = cuenta_file.read_text(encoding="utf-8").strip() if cuenta_file.exists() else None
            tel_val = tel_file.read_text(encoding="utf-8").strip() if tel_file.exists() else None
            nombre_val = nombre_file.read_text(encoding="utf-8").strip() if nombre_file.exists() else None
            
            hay_nueva_busqueda = False
            
            # 2. Evaluar prioridad de señales nuevas
            if cuenta_val:
                logger.info(f"🎯 Nueva señal de CUENTA detectada: {cuenta_val}")
                hay_nueva_busqueda = True
                
                # Consumir la señal para evitar bloqueos por valor duplicado y permitir futuras re-búsquedas
                try:
                    if cuenta_file.exists():
                        cuenta_file.unlink()
                except Exception as e:
                    logger.error(f"Error borrando archivo de señal cuenta.txt: {e}")

                # Asegurar estar en Pantalla Única de Consulta
                menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                if menu_tab:
                    driver.execute_script("arguments[0].click();", menu_tab)
                    time.sleep(2)

                # Clic en Consulta (Lupa)
                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_cuenta)
                if inp:
                    inp.clear()
                    inp.send_keys(cuenta_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info(f"🚀 Consulta de Cuenta ({cuenta_val}) enviada a Siebel.")
                    
                    last_query["cuenta"] = cuenta_val
                    last_query["tel"] = None
                    last_query["nombre"] = None
                else:
                    logger.error("No se localizó el campo de entrada de Cuenta.")
                    
            elif tel_val:
                logger.info(f"🎯 Nueva señal de TELÉFONO detectada: {tel_val}")
                hay_nueva_busqueda = True
                
                try:
                    if tel_file.exists():
                        tel_file.unlink()
                except Exception as e:
                    logger.error(f"Error borrando archivo de señal tel.txt: {e}")

                # Asegurar estar en Pantalla Única de Consulta
                menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                if menu_tab:
                    driver.execute_script("arguments[0].click();", menu_tab)
                    time.sleep(2)

                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_telefono)
                if inp:
                    inp.click()  # Habilitación visual de campo en Siebel
                    time.sleep(0.5)
                    inp.clear()
                    inp.send_keys(tel_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info(f"🚀 Consulta de Teléfono ({tel_val}) enviada a Siebel.")
                    
                    last_query["tel"] = tel_val
                    last_query["cuenta"] = None
                    last_query["nombre"] = None
                else:
                    logger.error("No se localizó el campo de entrada de Teléfonos.")
                    
            elif nombre_val:
                logger.info(f"🎯 Nueva señal de NOMBRE detectada: {nombre_val}")
                hay_nueva_busqueda = True
                
                try:
                    if nombre_file.exists():
                        nombre_file.unlink()
                except Exception as e:
                    logger.error(f"Error borrando archivo de señal nombre.txt: {e}")

                # Asegurar estar en Pantalla Única de Consulta
                menu_tab = bucleEncuentraItemsLong(driver, xpath_pantalla_unica)
                if menu_tab:
                    driver.execute_script("arguments[0].click();", menu_tab)
                    time.sleep(2)

                bucleEncuentraItemsClick(driver, xpath_btn_consulta)
                time.sleep(1)
                
                inp = bucleEncuentraItems(driver, xpath_input_nombre)
                if inp:
                    inp.clear()
                    inp.send_keys(nombre_val)
                    inp.send_keys(Keys.RETURN)
                    logger.info(f"🚀 Consulta de Nombre ({nombre_val}) enviada a Siebel.")
                    
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
