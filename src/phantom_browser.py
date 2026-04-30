import time
import logging
import threading
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

logger = logging.getLogger("PhantomBrowser")

class PhantomAgent:
    """Mantiene una sesión de Vicidial activa en segundo plano simulando a un agente humano en un navegador"""
    def __init__(self, host, phone, phone_pass, user, password, campaign):
        self.host = host
        self.phone = phone
        self.phone_pass = phone_pass
        self.user = user
        self.password = password
        self.campaign = campaign
        self.driver = None
        self._running = False
        self._thread = None
        
    def trigger_disposition(self, status="SALE"):
        """Fuerza al navegador a colgar y disponer de la llamada para evitar estatus DEAD"""
        if not self.driver: return
        
        logger.info(f"👻 [Phantom] Iniciando Auto-Disposición (Estatus: {status})...")
        try:
            # 1. Intentar colgar al cliente si no se ha colgado solo
            try:
                # El botón de hangup suele ser un elemento <a> con onclick que contiene 'Hangup'
                hangup_links = self.driver.find_elements(By.XPATH, "//*[contains(@onclick, 'HangUp')]")
                for link in hangup_links:
                    if link.is_displayed():
                        self.driver.execute_script("arguments[0].click();", link)
                        logger.info("👻 [Phantom] Clic en Hangup Customer.")
                        time.sleep(2)
                        break
            except:
                pass

            # 2. Seleccionar el estatus (Disposition)
            # En Vicidial es una lista de botones o links. Buscamos el que coincida con el status
            dispo_selectors = [
                f"//*[contains(text(), '{status}')]",
                f"//input[@value='{status}']",
                "//a[contains(@onclick, 'DispoSelectContent')]"
            ]
            
            for selector in dispo_selectors:
                try:
                    btn = self.driver.find_element(By.XPATH, selector)
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        logger.info(f"👻 [Phantom] Estatus {status} seleccionado.")
                        time.sleep(1)
                        break
                except:
                    continue

            # 3. Clic final en FINISHED
            try:
                finish_btn = self.driver.find_element(By.XPATH, "//input[@id='DispoDoneButton']")
                if finish_btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", finish_btn)
                    logger.info("👻 [Phantom] ¡Juego finalizado (FINISHED)! Listo para la siguiente.")
            except:
                # A veces se cierra solo al seleccionar el dispo
                pass

        except Exception as e:
            logger.error(f"👻 [Phantom] Error en Auto-Disposición: {e}")

    def _run_browser(self):

        logger.info("👻 [Phantom] Inicializando Navegador Headless...")
        
        # Crear un perfil de usuario temporal para aislar esta sesión de otras de Chrome
        tmp_user_data = tempfile.mkdtemp(prefix="phantom_chrome_")
        logger.info(f"👻 [Phantom] Usando perfil temporal: {tmp_user_data}")

        chrome_options = Options()
        # Usamos opciones ultra-estables para evitar cierres en Windows
        chrome_options.add_argument(f"--user-data-dir={tmp_user_data}")
        chrome_options.add_argument("--headless=old") # Modo clásico, el más estable para Windows
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--ignore-certificate-errors")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(45) # Más tiempo para el estadio
            
            # Usar URL de acceso directo (Bypass de formularios)
            direct_url = (
                f"http://{self.host}/agc/vicidial.php?"
                f"pl={self.phone}&pp={self.phone_pass}&"
                f"VD_login={self.user}&VD_pass={self.password}&"
                f"VD_campaign={self.campaign}&login_sub=SUBMIT"
            )
            
            logger.info(f"👻 [Phantom] Iniciando Sesión Directa para {self.user}...")
            self.driver.get(direct_url)
            
            # Dar tiempo para que el servidor procese el login y mande la llamada
            time.sleep(10)
            
            self.driver.save_screenshot("phantom_after_direct_login.png")
            logger.info(f"👻 [Phantom] Sesión Web Iniciada para {self.user}. Manteniendo latidos JS...")

            # Dar clic al botón RESUME automáticamente
            logger.info("👻 [Phantom] Esperando 5 segundos adicionales para estabilizar interfaz...")
            time.sleep(5)
            
            self.driver.save_screenshot("phantom_main_screen.png")

            try:
                # Intentar varios selectores para el botón de Resume/Ready
                resume_btn = None
                # ... (resto de selectores igual pero con manejo de errores)
                selectors = [
                    "//a[contains(@onclick, 'ReSume_PauSe')]",
                    "//input[@id='DialNextButton']",
                    "//*[contains(text(), 'RESUME')]",
                    "//*[contains(text(), 'READY')]"
                ]
                
                for selector in selectors:
                    try:
                        btn = self.driver.find_element(By.XPATH, selector)
                        if btn.is_displayed():
                            resume_btn = btn
                            break
                    except:
                        continue

                if resume_btn:
                    self.driver.execute_script("arguments[0].click();", resume_btn)
                    logger.info("👻 [Phantom] ¡Estatus puesto en RESUME! Don Pelayo está operando.")
                else:
                    logger.warning("👻 [Phantom] No encontré el botón RESUME. ¿Llamada de enlace fallida?")
            except Exception as e:
                logger.error(f"👻 [Phantom] Error al intentar poner READY: {e}")
            
            # Bucle para mantener script abierto y procesando JS
            while self._running:
                time.sleep(60)
                if self._running:
                    try:
                        self.driver.save_screenshot("phantom_heartbeat.png")
                        # Prevenir cierres por inactividad del navegador
                        self.driver.execute_script("window.scrollTo(0,0);")
                    except:
                        pass

        except Exception as e:
            logger.error(f"👻 [Phantom] Falla técnica en el navegador: {e}")
            if self.driver:
                self.driver.save_screenshot("phantom_crash_debug.png")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            # Limpiar el directorio temporal de perfil
            try:
                shutil.rmtree(tmp_user_data, ignore_errors=True)
                logger.info(f"👻 [Phantom] Perfil temporal eliminado: {tmp_user_data}")
            except:
                pass

            logger.info("👻 [Phantom] Navegador apagado.")


    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_browser, daemon=True)
        self._thread.start()
        
    def stop(self):
        if not self._running: return
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
