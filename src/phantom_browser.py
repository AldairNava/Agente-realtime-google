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
    "amex":        "3001",   # 3006 - Plata Card
    "plata":       "3001",   # 3006 - Plata Card (misma que amex)
    "retencion":   "3001",   # 3001 - retenciones IZZI
    "ventas_izzi": "3001",   # 3006 - Plata Card (misma que amex)
    "depuracion":  "3002",   # 3002 - Depuracion
    "inbot":       "3008",   # 3008 - Campania In BOT
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
        campaign_label = CAMPAIGN_SELECT_MAP.get(self.campania_name)
        try:
            select_el = self.driver.find_element(By.XPATH, '//*[@id="VD_campaign"]')
            select_el.click()
            time.sleep(1)

            # Intentar por texto visible del option
            if campaign_label:
                try:
                    option = self.driver.find_element(
                        By.XPATH, f'//select[@id="VD_campaign"]/option[contains(text(), "{self.campaign_id}")]')
                    option.click()
                    logger.info(f"👻 [Phantom] Campaña seleccionada por ID: {self.campaign_id}")
                    return
                except NoSuchElementException:
                    pass

            # Fallback: primera opción disponible
            options = self.driver.find_elements(By.XPATH, '//select[@id="VD_campaign"]/option')
            for opt in options:
                if self.campaign_id in opt.get_attribute("value") or self.campaign_id in opt.text:
                    opt.click()
                    logger.info(f"👻 [Phantom] Campaña seleccionada (fallback): {opt.text}")
                    return

            # Último fallback: segunda opción
            if len(options) > 1:
                options[1].click()
                logger.warning(f"👻 [Phantom] Campaña seleccionada por posición (opción 2): {options[1].text}")

        except Exception as e:
            logger.error(f"👻 [Phantom] Error seleccionando campaña: {e}")

    def _close_popup(self):
        """Cierra el popup de sesión duplicada si aparece."""
        try:
            ok = self.driver.find_element(
                By.XPATH, '//*[@id="DeactivateDOlDSessioNSpan"]/table/tbody/tr/td/font/a')
            ok.click()
            logger.info("👻 [Phantom] Popup de sesión duplicada cerrado.")
            time.sleep(2)
        except Exception:
            pass

    def _click_resume(self):
        """Pone el agente en estado DISPONIBLE/RESUME."""
        selectors = [
            '//*[@id="DiaLControl"]/a/img',          # Botón imagen de marcar/disponible
            "//a[contains(@onclick, 'ReSume_PauSe')]",
            "//input[@id='DialNextButton']",
            "//*[contains(text(), 'RESUME')]",
            "//*[contains(text(), 'READY')]",
        ]
        for xpath in selectors:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    logger.info("👻 [Phantom] ✅ Estado puesto en DISPONIBLE.")
                    return True
            except Exception:
                continue
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
        for intento in range(5):
            try:
                page_text = self.driver.find_element(By.TAG_NAME, 'body').text
                if 'No one is in your session' in page_text or 'Call Agent Again' in page_text:
                    logger.warning(f"👻 [Phantom] Vicidial dice 'No one in session' (intento {intento+1}). Reintentando...")
                    try:
                        btn = self.driver.find_element(By.LINK_TEXT, 'Call Agent Again')
                        btn.click()
                        logger.info("👻 [Phantom] Clic en 'Call Agent Again'.")
                        time.sleep(8)  # Esperar que Vicidial reintente llamar al softphone
                    except NoSuchElementException:
                        # Buscar por texto parcial
                        try:
                            btn = self.driver.find_element(By.PARTIAL_LINK_TEXT, 'Call Agent')
                            btn.click()
                            time.sleep(8)
                        except Exception:
                            break
                else:
                    break  # Ya no está en la página de error
            except Exception:
                break

        # --- Poner en DISPONIBLE ---
        self._click_resume()
        time.sleep(2)
        self.go_to_main_tab()

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
                    logger.info("👻 [Phantom] Iniciando Chrome usando Selenium Manager...")
                    self.driver = webdriver.Chrome(options=chrome_options)
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
