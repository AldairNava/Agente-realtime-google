import time
import logging
import threading
import tempfile
import shutil
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException, ElementClickInterceptedException,
    ElementNotInteractableException, JavascriptException
)

logger = logging.getLogger("PhantomBrowser")

# Silenciar advertencias inofensivas del pool de conexiones de Selenium (urllib3)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

# Mapa de campaña → valor exacto del <option> en el select de Vicidial
CAMPAIGN_SELECT_MAP = {
    "amex":        "3006",
    "plata":       "3006",
    "retencion":   "3001",
    "ventas_izzi": "TVVirt",
    "depuracion":  "3002",
    "inbot":       "3008",
}

class PhantomAgent:
    """
    Mantiene una sesión de Vicidial activa simulando un agente humano en Chrome.
    Realiza el proceso real de login de Vicidial (2 pasos + selección de campaña + Submit),
    igual que lo hace un agente humano desde el navegador.
    """
    def __init__(self, host, phone, phone_pass, user, password, campaign_id,
                 campania_name='amex'):
        self.host = host
        self.phone = phone                  # Extensión SIP (ej: 7929)
        self.phone_pass = phone_pass        # Password de la extensión
        self.user = user                    # Usuario agente (ej: dep1)
        self.password = password            # Password agente
        self.campaign_id = campaign_id      # ID numérico (ej: 5001)
        self.campania_name = campania_name  # Nombre clave (ej: ventas_izzi)
        self.driver = None
        self._running = False
        self._thread = None
        self.login_success = False

    # ------------------------------------------------------------------
    # Helpers de login
    # ------------------------------------------------------------------
    def _fill_login(self, username, password):
        """Rellena usuario y contraseña en el formulario de Vicidial."""
        user_field = self.driver.find_element(
            By.XPATH, '//*[@id="vicidial_form"]/center/table/tbody/tr[3]/td[2]/input')
        pass_field = self.driver.find_element(
            By.XPATH, '//*[@id="vicidial_form"]/center/table/tbody/tr[4]/td[2]/input')
        user_field.clear()
        user_field.send_keys(username)
        pass_field.clear()
        pass_field.send_keys(password)
        time.sleep(1)

    def _select_campaign(self):
        """Selecciona la campaña correcta en el <select> de Vicidial."""
        try:
            select_el = self.driver.find_element(By.XPATH, '//*[@id="VD_campaign"]')
            select_el.click()
            time.sleep(1)

            # Obtener todas las opciones disponibles
            options = self.driver.find_elements(By.XPATH, '//select[@id="VD_campaign"]/option')
            logger.info(f"👻 [Phantom] Opciones de campaña encontradas: {[opt.text for opt in options]}")

            if not options:
                logger.warning("👻 [Phantom] No se encontraron opciones en el select de campañas.")
                return

            # 1. Buscar si hay una opción que ya venga pre-seleccionada (designada) por el servidor (que no sea el placeholder vacío)
            designated_option = None
            for opt in options:
                val = (opt.get_attribute("value") or "").strip()
                if (opt.is_selected() or opt.get_attribute("selected") is not None) and val != "":
                    designated_option = opt
                    break

            if designated_option:
                val = (designated_option.get_attribute("value") or "").strip()
                designated_option.click()
                logger.info(f"👻 [Phantom] Campaña seleccionada (respetando designada por el servidor): {designated_option.text} (value={val})")
                return

            # 2. Si no hay pre-seleccionada, buscar una que coincida con self.campaign_id (ej. "pcardVir", "3006")
            if self.campaign_id:
                target_campaign = str(self.campaign_id).strip().lower()
                for opt in options:
                    val = (opt.get_attribute("value") or "").strip().lower()
                    if val == target_campaign:
                        opt.click()
                        logger.info(f"👻 [Phantom] Campaña seleccionada (coincidencia con campaign_id): {opt.text} (value={opt.get_attribute('value')})")
                        return

            # 3. Si no coincide, seleccionar la primera opción válida (con valor no vacío)
            selected_opt = None
            for opt in options:
                val = (opt.get_attribute("value") or "").strip()
                if val:
                    selected_opt = opt
                    break

            if selected_opt:
                selected_opt.click()
                logger.info(f"👻 [Phantom] Campaña seleccionada (primera opción válida disponible): {selected_opt.text} (value={selected_opt.get_attribute('value')})")
            else:
                # Fallback extremo por si acaso
                first_opt = options[0]
                first_opt.click()
                logger.info(f"👻 [Phantom] Campaña seleccionada (primera opción por fallback extremo): {first_opt.text} (value={first_opt.get_attribute('value')})")

        except Exception as e:
            logger.error(f"👻 [Phantom] Error seleccionando campaña: {e}")

    def _close_popup(self):
        """Cierra el popup de sesión duplicada si aparece, intentándolo repetidamente."""
        logger.info("👻 [Phantom] Buscando popup de sesión duplicada...")
        for i in range(10):
            try:
                # 1. Intentar buscar por ID y luego hacer click en enlace interno
                try:
                    span = self.driver.find_element(By.ID, "DeactivateDOlDSessioNSpan")
                    if span.is_displayed():
                        links = span.find_elements(By.TAG_NAME, "a")
                        for link in links:
                            if link.is_displayed():
                                link.click()
                                logger.info("👻 [Phantom] Popup de sesión duplicada cerrado haciendo clic en enlace interno.")
                                time.sleep(2)
                                return True
                except Exception:
                    pass

                # 2. Intentar XPath exacto
                ok = self.driver.find_element(
                    By.XPATH, '//*[@id="DeactivateDOlDSessioNSpan"]/table/tbody/tr/td/font/a')
                if ok.is_displayed():
                    ok.click()
                    logger.info("👻 [Phantom] Popup de sesión duplicada cerrado por XPATH.")
                    time.sleep(2)
                    return True
            except Exception:
                pass
            time.sleep(1)
        logger.info("👻 [Phantom] No se detectó popup de sesión duplicada activo.")
        return False

    def _click_resume(self):
        """Pone el agente en estado DISPONIBLE/RESUME."""
        selectors = [
            '//*[@id="DiaLControl"]/a/img',          # Botón imagen de marcar/disponible
            "//a[contains(@onclick, 'AutoDial_ReSume_PauSe')]",
            "//a[contains(@onclick, 'ReSume_PauSe')]",
            "//img[@alt='You are paused']",
            "//img[contains(@src, 'vdc_LB_paused.gif')]",
            "//input[@id='DialNextButton']",
            "//*[contains(text(), 'RESUME')]",
            "//*[contains(text(), 'READY')]",
        ]
        
        # 1. Intentar hacer clic en los elementos visuales
        for xpath in selectors:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    # Intentar clic estándar
                    try:
                        btn.click()
                        logger.info(f"👻 [Phantom] ✅ Estado puesto en DISPONIBLE haciendo clic en {xpath}.")
                        return True
                    except Exception:
                        pass
                    # Intentar clic por JS
                    self.driver.execute_script("arguments[0].click();", btn)
                    logger.info(f"👻 [Phantom] ✅ Estado puesto en DISPONIBLE haciendo clic por JS en {xpath}.")
                    return True
            except Exception:
                continue

        # 2. Fallback: Ejecutar la función JS directamente
        try:
            logger.info("👻 [Phantom] Intentando ejecutar AutoDial_ReSume_PauSe directamente vía JS...")
            self.driver.execute_script("AutoDial_ReSume_PauSe('VDADready','','','','','','','YES');")
            logger.info("👻 [Phantom] ✅ Estado puesto en DISPONIBLE ejecutando AutoDial_ReSume_PauSe vía JS.")
            return True
        except Exception as js_err:
            logger.debug(f"AutoDial_ReSume_PauSe no disponible: {js_err}")

        try:
            logger.info("👻 [Phantom] Intentando ejecutar ReSume_PauSe directamente vía JS...")
            self.driver.execute_script("ReSume_PauSe('VDADready','','','','','','','YES');")
            logger.info("👻 [Phantom] ✅ Estado puesto en DISPONIBLE ejecutando ReSume_PauSe vía JS.")
            return True
        except Exception as js_err:
            logger.debug(f"ReSume_PauSe no disponible: {js_err}")

        logger.warning("👻 [Phantom] No se encontró botón RESUME/DISPONIBLE.")
        return False

    # ------------------------------------------------------------------
    # Login completo (2 pasos como el agente humano)
    # ------------------------------------------------------------------
    def _do_login(self):
        """
        Proceso de login real de Vicidial:
        1) Navegar a la URL del panel
        2) Login con extensión + password de extensión → Submit
        3) Login con usuario agente + password → seleccionar campaña → Submit
        4) Cerrar popup si aparece
        5) Clic en DISPONIBLE
        """
        url = f"http://{self.host}/agc/vicidial.php"
        logger.info(f"👻 [Phantom] Navegando a: {url}")
        self.driver.get(url)
        time.sleep(3)

        # --- Paso 1: Login con extensión ---
        logger.info(f"👻 [Phantom] Paso 1: Login con extensión {self.phone}...")
        self._fill_login(self.phone, self.phone_pass)
        # Clic en Submit del primer formulario
        self.driver.find_element(
            By.XPATH, '//*[@id="vicidial_form"]/center/table/tbody/tr[5]/td/input').click()
        time.sleep(3)

        # --- Paso 2: Login con usuario agente ---
        logger.info(f"👻 [Phantom] Paso 2: Login con usuario {self.user}...")
        self._fill_login(self.user, self.password)
        time.sleep(1)

        # --- Seleccionar campaña ---
        logger.info(f"👻 [Phantom] Seleccionando campaña {self.campaign_id}...")
        self._select_campaign()
        time.sleep(2)

        # --- Submit final ---
        logger.info("👻 [Phantom] Enviando formulario final (Submit)...")
        self.driver.find_element(
            By.XPATH, '/html/body/form/center/table/tbody/tr[6]/td/input').click()
        time.sleep(5)

        # --- Cerrar popup si existe ---
        self._close_popup()
        time.sleep(3)

        # --- Verificar si Vicidial muestra "No one is in your session" ---
        # Esto ocurre cuando el softphone (pyVoIP) no contestó a tiempo la llamada del agente.
        # En ese caso hacemos clic en "Call Agent Again" hasta que la sesión se establezca.
        for intento in range(8):
            try:
                page_text = (self.driver.find_element(By.TAG_NAME, 'body').text or "").strip()
                if not page_text:
                    time.sleep(1)
                    continue
                    
                if 'No one is in your session' in page_text or 'Call Agent Again' in page_text:
                    logger.warning(f"👻 [Phantom] Vicidial dice 'No one in session' (intento {intento+1}). Reintentando...")
                    try:
                        btn = self.driver.find_element(By.LINK_TEXT, 'Call Agent Again')
                        btn.click()
                        logger.info("👻 [Phantom] Clic en 'Call Agent Again'.")
                        time.sleep(8)  # Esperar que Vicidial reintente llamar al softphone
                    except NoSuchElementException:
                        try:
                            btn = self.driver.find_element(By.PARTIAL_LINK_TEXT, 'Call Agent')
                            btn.click()
                            time.sleep(8)
                        except Exception:
                            time.sleep(2)
                else:
                    # Si no está en error y ya vemos indicios del panel principal (como las pestañas)
                    if self.driver.find_elements(By.XPATH, '//*[@id="Tabs"]') or self.driver.find_elements(By.XPATH, "//img[@alt='MAIN']"):
                        logger.info("👻 [Phantom] Interfaz principal de agente detectada exitosamente.")
                        break
                    time.sleep(1)
            except Exception as e:
                # Si hay un error temporal de carga, esperar y reintentar en vez de romper el ciclo
                logger.debug(f"👻 [Phantom] Esperando carga de página en check de sesión ({e})...")
                time.sleep(1)

        # --- Poner en DISPONIBLE ---
        logger.info("👻 [Phantom] Esperando a que la interfaz esté lista para ponerse en DISPONIBLE...")
        success = False
        for intento in range(6):
            if self._click_resume():
                success = True
                break
            logger.info(f"👻 [Phantom] Reintentando poner en DISPONIBLE en 3 segundos (intento {intento+2}/6)...")
            time.sleep(3)
        
        if not success:
            logger.warning("👻 [Phantom] No se pudo poner al agente en DISPONIBLE tras varios intentos.")
            
        time.sleep(2)
        
        # --- Regresar a la pestaña MAIN ---
        success_tab = False
        for intento in range(4):
            if self.go_to_main_tab():
                success_tab = True
                break
            time.sleep(2)
        if not success_tab:
            logger.warning("👻 [Phantom] No se pudo cambiar a la pestaña MAIN.")

    # ------------------------------------------------------------------
    # Hilo principal del navegador
    # ------------------------------------------------------------------
    def _run_browser(self):
        tmp_user_data = tempfile.mkdtemp(prefix="phantom_chrome_")
        logger.info(f"👻 [Phantom] Perfil temporal: {tmp_user_data}")

        chrome_options = Options()
        chrome_options.add_argument(f"--user-data-dir={tmp_user_data}")
        # Sin --headless para que puedas ver el navegador
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--ignore-certificate-errors")

        login_success = False
        try:
            while self._running and not login_success:
                try:
                    if self.driver:
                        self.driver.quit()
                    
                    from src.driver_manager import crear_chrome_driver
                    self.driver = crear_chrome_driver(chrome_options)
                    self.driver.set_page_load_timeout(45)

                    self._do_login()
                    login_success = True
                    self.login_success = True
                    logger.info(f"👻 [Phantom] ✅ Sesión Vicidial activa para {self.user} | Campaña: {self.campania_name.upper()}")

                except Exception as e:
                    self.login_success = False
                    logger.error(f"👻 [Phantom] Error en login: {e}. Reintentando en 5s...")
                    if not self._running:
                        break
                    time.sleep(5)

            # Bucle de latidos para mantener viva la sesión
            while self._running:
                time.sleep(30)
                if self._running:
                    try:
                        self.driver.execute_script("window.scrollTo(0,0);")
                    except Exception:
                        logger.warning("👻 [Phantom] Pérdida de sesión en latido.")
                        break

        except Exception as e:
            logger.error(f"👻 [Phantom] Falla técnica: {e}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
            try:
                shutil.rmtree(tmp_user_data, ignore_errors=True)
            except Exception:
                pass
            logger.info("👻 [Phantom] Navegador apagado.")

    def _is_browser_alive(self) -> bool:
        """Comprueba si el driver de Chrome sigue activo. Si el usuario cerró la ventana, retorna False."""
        if not self.driver:
            return False
        try:
            _ = self.driver.window_handles  # Lanza si el browser está muerto
            return True
        except Exception:
            return False

    def is_call_hungup(self) -> bool:
        """Verifica si el cliente ha colgado en la interfaz de Vicidial.
        
        También retorna True si el usuario cerró manualmente el navegador Chrome,
        lo que hace que el agente se apague limpiamente.
        """
        if not self._running:
            return False

        # --- Detección de cierre manual del navegador ---
        if not self._is_browser_alive():
            logger.warning("👻 [Phantom] ⚠️ El navegador fue cerrado manualmente. Señalando fin de sesión al agente...")
            self._running = False  # Detener el hilo interno
            return True

        try:
            # 1. Comprobar indicador visual de estado (GIF DEAD.gif) de la barra de pestañas
            try:
                img_el = self.driver.find_element(By.XPATH, '//*[@id="Tabs"]/table/tbody/tr/td[5]/img')
                src = img_el.get_attribute("src")
                if src and 'DEAD.gif' in src:
                    logger.info("👻 [Phantom] Detectado GIF 'DEAD.gif' en barra de pestañas. La llamada ha colgado.")
                    return True
            except Exception:
                pass

            # 2. Respaldo: Buscar texto "CALL HUNGUP" en el código fuente HTML de forma directa
            source = self.driver.page_source
            if "CALL HUNGUP" in source:
                logger.info("👻 [Phantom] Detectado texto 'CALL HUNGUP' en el HTML. La llamada ha colgado.")
                return True

            # 3. Respaldo 2: XPath tradicional
            elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'CALL HUNGUP')]")
            if len(elements) > 0:
                logger.info("👻 [Phantom] Elemento XPATH con 'CALL HUNGUP' encontrado. La llamada ha colgado.")
                return True

            return False
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error comprobando colgado (posible cierre de ventana): {e}")
            logger.warning("👻 [Phantom] Asumiendo fin de sesión por error irrecuperable del browser.")
            self._running = False
            return True

    def is_in_call(self) -> bool:
        """Verifica si el agente está en una llamada activa basándose en la imagen 'livecall' (ON/OFF)."""
        if not self._running or not self.driver:
            return False

        if not self._is_browser_alive():
            return False

        def check_livecall_img(d):
            try:
                # Buscar el elemento de imagen por su atributo name="livecall"
                img = d.find_element(By.NAME, "livecall")
                src = img.get_attribute("src") or ""
                if "live_call_ON" in src:
                    return True
                elif "live_call_OFF" in src:
                    return False
            except Exception:
                pass
            return None

        try:
            # 1. Intentar buscar en el DOM principal
            res = check_livecall_img(self.driver)
            if res is not None:
                return res

            # 2. Buscar dentro de los iframes si no se encontró en el DOM principal
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    res = check_livecall_img(self.driver)
                    self.driver.switch_to.default_content()
                    if res is not None:
                        return res
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass

            return False
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error comprobando llamada activa con live_call img: {e}")
            return False

    def get_lead_id_fast(self) -> str:
        """Obtiene de forma ultra-rápida el lead_id de la interfaz usando JS."""
        if not self._running or not self.driver:
            return ""
        try:
            return str(self.driver.execute_script("return document.getElementById('lead_id') ? document.getElementById('lead_id').value : '';")).strip()
        except Exception:
            return ""

    def is_on_dispo_screen(self) -> bool:
        """Retorna True si el navegador está en la pantalla de selección de disposición."""
        if not self._running or not self.driver:
            return False
        
        def check_driver(d):
            try:
                el = d.find_element(By.ID, "DispoSelectForm")
                if el.is_displayed():
                    return True
            except Exception:
                try:
                    el = d.find_element(By.NAME, "DispoSelectForm")
                    if el.is_displayed():
                        return True
                except Exception:
                    pass
            return False

        try:
            if check_driver(self.driver):
                return True
            
            # Buscar en iframes
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    self.driver.switch_to.frame(iframe)
                    found = check_driver(self.driver)
                    self.driver.switch_to.default_content()
                    if found:
                        return True
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error comprobando dispo en navegador: {e}")
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
        return False

    def go_to_script_tab(self) -> bool:
        """Hace clic en la pestaña SCRIPT del panel de agente."""
        if not self._running or not self.driver:
            return False
        
        selectors = [
            "//img[@alt='SCRIPT']",
            "//img[contains(@src, 'vdc_tab_script')]",
            "//a[contains(@onclick, 'vdc_tab_script')]",
            "//font[contains(text(), 'SCRIPT')]",
            "//span[contains(text(), 'SCRIPT')]"
        ]
        
        for selector in selectors:
            try:
                el = self.driver.find_element(By.XPATH, selector)
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].click();", el)
                    logger.info(f"👻 [Phantom] Clic exitoso en pestaña SCRIPT usando selector: {selector}")
                    return True
            except Exception:
                continue
                
        logger.warning("👻 [Phantom] No se pudo encontrar o hacer clic en la pestaña SCRIPT.")
        return False

    def go_to_main_tab(self) -> bool:
        """Hace clic en la pestaña MAIN (logo/pestaña principal del panel de agente)."""
        if not self._running or not self.driver:
            return False
        
        selectors = [
            "//img[@alt='MAIN']",
            "//img[contains(@src, 'vicidial_admin_web_logo')]",
            "//a[contains(@onclick, 'vdc_tab_main')]",
            "//font[contains(text(), 'MAIN')]",
            "//span[contains(text(), 'MAIN')]"
        ]
        
        for selector in selectors:
            try:
                el = self.driver.find_element(By.XPATH, selector)
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].click();", el)
                    logger.info(f"👻 [Phantom] Clic exitoso en pestaña MAIN usando selector: {selector}")
                    return True
            except Exception:
                continue
                
        logger.warning("👻 [Phantom] No se pudo encontrar o hacer clic en la pestaña MAIN.")
        return False

    def get_active_call_data(self) -> dict:
        """
        Lee la información de la llamada activa (first_name, last_name, phone_number, lead_id)
        desde la interfaz del navegador, buscando en el DOM principal y en todos los iframes.
        """
        data = {
            "first_name": "",
            "last_name": "",
            "phone_number": "",
            "lead_id": "",
            "Nombre_titular": "",
            "CUENTA": ""
        }
        
        if not self._running or not self.driver:
            return data
            
        def extract_from_driver(d):
            res = {}
            fields_to_check = ["first_name", "last_name", "phone_number", "lead_id", "Nombre_titular", "CUENTA"]
            for field in fields_to_check:
                val = ""
                try:
                    el = d.find_element(By.ID, field)
                    val = el.get_attribute("value") or el.text or ""
                except NoSuchElementException:
                    try:
                        el = d.find_element(By.NAME, field)
                        val = el.get_attribute("value") or el.text or ""
                    except NoSuchElementException:
                        if field == "Nombre_titular":
                            try:
                                # XPath de respaldo para el span que contiene el Nombre_titular
                                el = d.find_element(By.XPATH, "//*[@id='field_content_Nombre_titular']")
                                val = el.text or el.get_attribute("innerText") or ""
                            except NoSuchElementException:
                                pass
                        elif field == "CUENTA":
                            try:
                                # XPath de respaldo para el span que contiene CUENTA
                                el = d.find_element(By.XPATH, "//*[@id='field_content_CUENTA']")
                                val = el.text or el.get_attribute("innerText") or ""
                            except NoSuchElementException:
                                pass
                if val:
                    res[field] = val.strip()
            return res

        try:
            # 1. Intentar en el DOM principal
            main_res = extract_from_driver(self.driver)
            for k, v in main_res.items():
                if v:
                    data[k] = v
            
            # 2. Si falta el primer nombre o teléfono, buscar dentro de todos los iframes
            if not data["first_name"] and not data["Nombre_titular"]:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for index, iframe in enumerate(iframes):
                    try:
                        self.driver.switch_to.frame(iframe)
                        iframe_res = extract_from_driver(self.driver)
                        self.driver.switch_to.default_content()
                        for k, v in iframe_res.items():
                            if v:
                                data[k] = v
                    except Exception:
                        try:
                            self.driver.switch_to.default_content()
                        except Exception:
                            pass
                        continue
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error al buscar campos de llamada en navegador: {e}")
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
        
        # Normalizar Nombre_titular si se encontró para dividirlo en first_name y last_name
        full_name = data.get("Nombre_titular", "").strip()
        if full_name:
            parts = full_name.split()
            if parts:
                data["first_name"] = parts[0]
                data["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
                
        return data

    def get_session_details(self) -> dict:
        """
        Obtiene los detalles de la sesión activa de Vicidial (session_name, campaign, lead_id, phone_number)
        desde la interfaz del navegador, buscando variables globales o campos ocultos.
        """
        details = {
            "session_name": "",
            "campaign": "",
            "lead_id": "",
            "phone_number": "",
            "server_ip": self.host
        }
        if not self._running or not self.driver:
            return details
            
        js_script = """
        function findVal(name) {
            // Check global variable
            if (typeof window[name] !== 'undefined' && window[name] !== null) {
                var g = window[name];
                // If it is a string or number, return it
                if (typeof g === 'string' || typeof g === 'number') {
                    if (g !== '') return String(g);
                }
                // If it is an HTML element (exposed by ID in modern browsers), read its properties
                if (g && (g.nodeType || g.tagName)) {
                    if (g.value) return String(g.value);
                    if (g.innerText) return String(g.innerText).trim();
                    if (g.textContent) return String(g.textContent).trim();
                }
            }
            // Check inputs in main document
            var el = document.getElementsByName(name)[0] || document.getElementById(name);
            if (el) {
                return el.value || el.innerText || el.textContent || '';
            }
            
            // Check in iframes
            var iframes = document.getElementsByTagName('iframe');
            for (var i = 0; i < iframes.length; i++) {
                try {
                    var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                    var ifEl = doc.getElementsByName(name)[0] || doc.getElementById(name);
                    if (ifEl) {
                        return ifEl.value || ifEl.innerText || ifEl.textContent || '';
                    }
                } catch(e) {}
            }
            return '';
        }
        return {
            session_name: findVal('session_name'),
            campaign: findVal('campaign'),
            lead_id: findVal('lead_id'),
            phone_number: findVal('phone_number')
        };
        """
        try:
            res = self.driver.execute_script(js_script)
            if res:
                for k, v in res.items():
                    if v:
                        if isinstance(v, str):
                            details[k] = v.strip()
                        elif hasattr(v, "get_attribute") or hasattr(v, "text"):
                            # Es un WebElement. Extraer su valor o texto.
                            try:
                                details[k] = (v.get_attribute("value") or v.text or "").strip()
                            except Exception:
                                pass
                        else:
                            details[k] = str(v).strip()
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error obteniendo variables de sesión mediante JS: {e}")
            
        # Fallbacks usando Selenium directo
        for key in ["session_name", "campaign", "lead_id", "phone_number"]:
            if not details[key]:
                try:
                    el = self.driver.find_element(By.NAME, key)
                    details[key] = el.get_attribute("value") or el.text or ""
                except Exception:
                    try:
                        el = self.driver.find_element(By.ID, key)
                        details[key] = el.get_attribute("value") or el.text or ""
                    except Exception:
                        pass
        return details

    def set_pause_code(self, code: str) -> bool:
        """Establece un código de pausa ejecutando la función JS nativa de Vicidial."""
        if not self._running or not self.driver:
            logger.warning("👻 [Phantom] No se puede establecer código de pausa: navegador inactivo.")
            return False
        try:
            logger.info(f"👻 [Phantom] Intentando establecer código de pausa '{code}' mediante JS...")
            self.driver.execute_script(f"PauseCodeSelect_submit('{code}', 'YES');")
            logger.info(f"👻 [Phantom] ✅ Código de pausa '{code}' enviado con éxito mediante JS.")
            return True
        except Exception as e:
            logger.error(f"👻 [Phantom] Error al ejecutar PauseCodeSelect_submit vía JS: {e}")
            return False
    def logout_and_stop(self):
        """Intenta hacer un logout limpio de Vicidial y luego apaga el navegador."""
        if not self._running or not self.driver:
            return
        try:
            logger.info("👻 [Phantom] Intentando hacer logout limpio de Vicidial...")
            # Intentar hacer clic en el enlace/botón de LOGOUT
            # En Vicidial, suele ser un link que contiene "LOGOUT" o tiene una función "LogOuT"
            selectors = [
                "//a[contains(@href, 'LogOuT')]",
                "//a[contains(@onclick, 'LogOuT')]",
                "//a[contains(@onclick, 'normal_logout')]",
                "//*[contains(text(), 'LOGOUT')]",
                "//*[contains(text(), 'Log Out')]"
            ]
            for selector in selectors:
                try:
                    btn = self.driver.find_element(By.XPATH, selector)
                    if btn.is_displayed():
                        btn.click()
                        logger.info(f"👻 [Phantom] ✅ Clic en botón logout de Vicidial ({selector}).")
                        time.sleep(3)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error durante el proceso de logout: {e}")
        finally:
            self.stop()

    def hangup_call_browser(self) -> bool:
        """Intenta colgar la llamada activa simulando el clic o ejecutando la función JS en el navegador."""
        if not self._running or not self.driver:
            logger.warning("👻 [Phantom] No se puede colgar la llamada: navegador inactivo.")
            return False
        
        js_code = """
        try {
            if (typeof window.main_hangup_link_clicked === 'function') {
                window.main_hangup_link_clicked();
                return 'SUCCESS: main_hangup_link_clicked';
            }
            if (typeof window.ctHangUp === 'function') {
                window.ctHangUp();
                return 'SUCCESS: ctHangUp';
            }
            var el = document.getElementById('HeaderHangupLink') || 
                     document.getElementById('HangupLink') || 
                     document.getElementById('Hangup') ||
                     document.querySelector('a[href*="hangup"]') ||
                     document.querySelector('a[onclick*="hangup"]');
            if (el) {
                el.click();
                return 'SUCCESS: Element click';
            }
            // Buscar en iframes
            var iframes = document.getElementsByTagName('iframe');
            for (var i = 0; i < iframes.length; i++) {
                try {
                    var win = iframes[i].contentWindow;
                    var doc = iframes[i].contentDocument || win.document;
                    if (typeof win.main_hangup_link_clicked === 'function') {
                        win.main_hangup_link_clicked();
                        return 'SUCCESS: main_hangup_link_clicked in iframe';
                    }
                    var ifEl = doc.getElementById('HeaderHangupLink') || 
                               doc.getElementById('HangupLink') || 
                               doc.getElementById('Hangup') ||
                               doc.querySelector('a[href*="hangup"]') ||
                               doc.querySelector('a[onclick*="hangup"]');
                    if (ifEl) {
                        ifEl.click();
                        return 'SUCCESS: Element click in iframe';
                    }
                } catch(e) {}
            }
            return 'ERROR: No hangup function or element found';
        } catch(err) {
            return 'ERROR: ' + err.message;
        }
        """
        try:
            logger.info("🖥️ [Phantom] Intentando colgar llamada a través del navegador...")
            res = self.driver.execute_script(js_code)
            logger.info(f"VICIDIAL JS [hangup_call_browser]: {res}")
            return "SUCCESS" in str(res)
        except Exception as e:
            logger.error(f"Error al colgar llamada en el navegador: {e}")
            return False

    def resume_agent(self) -> bool:
        """Pone al agente en estado DISPONIBLE (RESUME)."""
        if not self._running or not self.driver:
            logger.warning("👻 [Phantom] No se puede resumir el agente: navegador inactivo.")
            return False
        try:
            logger.info("🖥️ [Phantom] Intentando poner al agente en DISPONIBLE...")
            return self._click_resume()
        except Exception as e:
            logger.error(f"Error al resumir el agente en el navegador: {e}")
            return False

    def logout_and_stop(self):
        """Intenta hacer un logout limpio de Vicidial y luego apaga el navegador."""
        if not self._running or not self.driver:
            return
        try:
            logger.info("👻 [Phantom] Intentando hacer logout limpio de Vicidial...")
            # Intentar hacer clic en el enlace/botón de LOGOUT
            # En Vicidial, suele ser un link que contiene "LOGOUT" o tiene una función "LogOuT"
            selectors = [
                "//a[contains(@href, 'LogOuT')]",
                "//a[contains(@onclick, 'LogOuT')]",
                "//a[contains(@onclick, 'normal_logout')]",
                "//*[contains(text(), 'LOGOUT')]",
                "//*[contains(text(), 'Log Out')]"
            ]
            for selector in selectors:
                try:
                    btn = self.driver.find_element(By.XPATH, selector)
                    if btn.is_displayed():
                        btn.click()
                        logger.info(f"👻 [Phantom] ✅ Clic en botón logout de Vicidial ({selector}).")
                        time.sleep(3)
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"👻 [Phantom] Error durante el proceso de logout: {e}")
        finally:
            self.stop()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_browser, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self.login_success = False
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
