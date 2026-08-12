"""
RPA de Retención izzi
=====================
Proceso autónomo que mantiene sesión en https://retencion-rpa.izzi.local/
y reacciona a señales TXT escritas por el agente de voz.

Señales esperadas (directorio rpa_signals/):
  cuenta.txt       → número de cuenta del cliente
  cancelacion.txt  → "total" o "parcial"
  motivo.txt       → texto del motivo de cancelación

Uso:
  py -3.12 tools/retencion_rpa.py
  py -3.12 tools/retencion_rpa.py --test   (modo debug visible)
"""

import os
import sys
import time
import logging
import argparse
import threading
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException, WebDriverException

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_URL       = "https://retencion-rpa.izzi.local"
LOGIN_URL      = f"{BASE_URL}/log-in?"
USERNAME       = "p-ccorrea"
PASSWORD       = "Crisco960427$"

_SCRIPT_DIR    = Path(__file__).parent.parent.parent   # raíz del proyecto
sys.path.append(str(_SCRIPT_DIR))
SIGNALS_DIR    = _SCRIPT_DIR / "assets" / "retencion" / "rpa_signals"

# Tiempos (segundos)
POLL_INTERVAL  = 0.3   # intervalo de sondeo DOM / archivos
MAX_WAIT       = 120   # timeout máximo de espera de elemento o señal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - RetencionRPA - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("RetencionRPA")


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------
class RetencionRPA:
    """Controla el navegador del portal de Retención durante una sesión de agente."""

    def __init__(self, headless: bool = False):
        self.headless  = headless
        self.driver    = None
        self._stop_evt = threading.Event()
        self._thread   = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self):
        """Abre el navegador, hace login y lanza el watcher en un hilo."""
        SIGNALS_DIR.mkdir(exist_ok=True)
        self._clear_signals()
        self._init_driver()
        self._login()
        logger.info("✅ Sesión activa. Iniciando vigilancia de señales...")
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el watcher y cierra el navegador."""
        logger.info("🛑 Deteniendo RPA de Retención...")
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        logger.info("✅ RPA detenido.")

    # ------------------------------------------------------------------
    # Inicialización del driver
    # ------------------------------------------------------------------
    def _init_driver(self):
        opts = Options()
        profile_dir = _SCRIPT_DIR / "assets" / "retencion" / "chrome_profile_retencion"
        
        perfil_nuevo = not profile_dir.exists()
        
        # Si el perfil es nuevo, forzamos modo visible para permitir la instalación de la extensión
        if self.headless and not perfil_nuevo:
            opts.add_argument("--headless=new")
            
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--ignore-ssl-errors")
        opts.add_argument("--allow-insecure-localhost")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--start-maximized")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

        # Perfil persistente para conservar cookies, sesiones y la extensión instalada
        opts.add_argument(f"--user-data-dir={str(profile_dir.absolute())}")

        if perfil_nuevo:
            logger.warning("=" * 80)
            logger.warning("❌ PERFIL DE CHROME NUEVO DETECTADO (RETENCIÓN)")
            logger.warning("Se abrirá el navegador para que instales la extensión de RPA.")
            logger.warning("Favor de instalar la extensión en la ventana de Chrome que se abrirá.")
            logger.warning("Una vez instalada, cierra el navegador y vuelve a iniciar este RPA.")
            logger.warning("=" * 80)
            
            logger.info("🌐 Iniciando Chrome visible...")
            from src.driver_manager import crear_chrome_driver
            self.driver = crear_chrome_driver(opts)
            
            extension_url = "https://chromewebstore.google.com/detail/rpa-extension/ccilojpjnmepojkjkdpohdkbjpkfoojd"
            logger.info(f"📦 Navegando a la Chrome Web Store: {extension_url}")
            self.driver.get(extension_url)
            
            try:
                self.driver.execute_script(
                    "alert('El perfil de Chrome es nuevo.\\n\\nPor favor, instala la extensión de RPA en este navegador.\\n\\nUna vez instalada, presiona ENTER en la consola de comandos para finalizar y luego reinicia el RPA.');"
                )
            except Exception:
                pass
                
            input("\n👉 Presiona ENTER aquí en la consola después de instalar la extensión para finalizar...")
            
            try:
                self.driver.quit()
            except Exception:
                pass
            logger.info("👋 Navegador cerrado. Por favor inicia el RPA de nuevo.")
            sys.exit(0)

        from src.driver_manager import crear_chrome_driver
        self.driver = crear_chrome_driver(opts)
        logger.info("🌐 Navegador iniciado.")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def _login(self):
        # ── 1. Navegar al portal de retención ───────────────────────────────
        logger.info(f"🔐 Navegando a {LOGIN_URL} ...")
        try:
            self.driver.get(LOGIN_URL)
            time.sleep(3)  # Esperar redirección o carga inicial
        except Exception as e:
            logger.error(f"❌ Error al cargar {LOGIN_URL}: {e}")
            logger.warning("⚠️ Es posible que el dominio local no sea resoluble en esta red. Manteniendo el navegador abierto en espera...")
            while True:
                time.sleep(5)

        # ── 2. Validar si ya estamos logueados (sesión activa en perfil persistente) ─────
        current_url = self.driver.current_url.lower()
        if "/home" in current_url:
            logger.info("ℹ️ Sesión activa detectada en URL (/home). Saltando login.")
            return

        # Intentar buscar el input de cuenta de forma silenciosa para ver si ya estamos en home
        try:
            cuenta_el = self.driver.find_element(
                By.CSS_SELECTOR,
                "input[placeholder*='cuenta'], input[placeholder*='Cuenta'], input[placeholder*='Número']"
            )
            if cuenta_el and cuenta_el.is_displayed():
                logger.info("ℹ️ Input de cuenta visible. Ya estamos logueados. Saltando login.")
                return
        except Exception:
            pass

        # ── 3. Llenar campos — name='email' y type='password' ───────────────
        logger.info("🔐 No se detectó sesión activa. Procediendo a loguear...")
        user_input = self._wait_for_element(By.CSS_SELECTOR, "input[name='email']", timeout=20)
        if user_input is None:
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
            user_input = next((i for i in inputs if i.is_displayed()), None)

        pass_input = self._wait_for_element(By.CSS_SELECTOR, "input[name='password']", timeout=15)

        if user_input is None or pass_input is None:
            raise RuntimeError("❌ No se encontraron los campos de login ni la pantalla de inicio.")

        user_input.clear()
        user_input.send_keys(USERNAME)   # solo "p-ccorrea", sin @izzi.mx
        pass_input.clear()
        pass_input.send_keys(PASSWORD)
        logger.info("✏️ Credenciales escritas.")

        # ── 4. Clic en "Iniciar sesion" con JS ──────────────────────────────
        btn = self._wait_for_element(
            By.XPATH,
            "//button[contains(normalize-space(text()),'Iniciar') or "
            "contains(normalize-space(text()),'iniciar') or "
            "contains(normalize-space(text()),'Ingresar')]",
            timeout=10
        )
        if btn:
            self.driver.execute_script("arguments[0].click();", btn)
            logger.info("🖱️ Clic JS en 'Iniciar sesion'.")
        else:
            pass_input.send_keys(Keys.RETURN)
            logger.info("↩️ Fallback: Enter en contraseña.")

        logger.info("⏳ Esperando pantalla principal...")

        # ── 5. Confirmar login: esperar que la URL cambie de /log-in ──────────
        deadline = time.time() + 60
        while time.time() < deadline:
            if "/log-in" not in self.driver.current_url:
                break
            time.sleep(POLL_INTERVAL)
        else:
            raise RuntimeError("❌ Login fallido — la URL no cambió después de 60s.")

        logger.info(f"✅ Login exitoso. URL: {self.driver.current_url}")
        logger.info("✅ Listo para recibir número de cuenta.")

    def _install_extension_from_store(self):
        """
        Navega directo a la Chrome Web Store e instala la extensión si no está instalada.
        """
        store_url = "https://chromewebstore.google.com/detail/rpa-extension/ccilojpjnmepojkjkdpohdkbjpkfoojd"
        logger.info(f"📦 Navegando directamente a Chrome Web Store: {store_url}")
        self.driver.get(store_url)
        time.sleep(5)  # Esperar renderizado

        # Buscar el botón por texto o tag
        btn_instalar = None
        deadline = time.time() + 15
        while time.time() < deadline:
            btns = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in btns:
                try:
                    txt = btn.text.strip().lower()
                    if "agregar a chrome" in txt or "add to chrome" in txt:
                        btn_instalar = btn
                        break
                    elif "quitar de chrome" in txt or "remove from chrome" in txt:
                        logger.info("ℹ️ La extensión ya se encuentra instalada.")
                        return
                except Exception:
                    pass
            if btn_instalar:
                break
            time.sleep(1)

        if btn_instalar:
            logger.info(f"🖱️ Botón '{btn_instalar.text}' encontrado. Dando clic para instalar...")
            self.driver.execute_script("arguments[0].click();", btn_instalar)
            
            # Esperar a que el usuario confirme o se complete (espera de 8s para el popup de confirmación)
            logger.info("⏳ Esperando confirmación de instalación (8s)...")
            time.sleep(8)
        else:
            logger.warning("⚠️ No se encontró el botón de 'Agregar a Chrome'. Es posible que ya esté instalada o requiera atención.")

    # ------------------------------------------------------------------
    # Loop de vigilancia de señales
    # ------------------------------------------------------------------
    def _watch_loop(self):
        """Hilo que vigila el directorio de señales y reacciona en orden."""
        logger.info("👀 Watcher iniciado. Esperando señales en rpa_signals/...")
        while not self._stop_evt.is_set():
            # --- Señal 1: cuenta ---
            cuenta = self._read_signal("cuenta.txt")
            if cuenta:
                logger.info(f"📨 Señal CUENTA recibida: {cuenta}")
                self._handle_cuenta(cuenta)
                # Después de cargar la cuenta, esperar cancelacion
                # --- Señal 2: cancelacion ---
                logger.info("⏳ Esperando señal de tipo de cancelación...")
                cancelacion = self._wait_for_signal("cancelacion.txt")
                if cancelacion:
                    logger.info(f"📨 Señal CANCELACION recibida: {cancelacion}")
                    self._handle_cancelacion(cancelacion)
                    # --- Señal 3: motivo ---
                    logger.info("⏳ Esperando señal de motivo...")
                    motivo = self._wait_for_signal("motivo.txt")
                    if motivo:
                        logger.info(f"📨 Señal MOTIVO recibida: {motivo}")
                        self._handle_motivo(motivo)
                        logger.info("🏁 Flujo de retención completado. Esperando nueva llamada...")
                        # Volver al inicio para la próxima llamada
                        self._return_to_home()
            time.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Acciones por señal
    # ------------------------------------------------------------------
    def _handle_cuenta(self, cuenta: str):
        """Ingresa el número de cuenta y hace clic en Siguiente."""
        try:
            # Si no estamos en home, navegar ahí
            if "/home" not in self.driver.current_url and "/log-in" not in self.driver.current_url:
                self.driver.get(f"{BASE_URL}/home")

            # Localizar el input de cuenta
            cuenta_input = self._wait_for_element(
                By.CSS_SELECTOR,
                "input[placeholder*='cuenta'], input[placeholder*='Cuenta'], input[placeholder*='Número']",
                timeout=30
            )
            if cuenta_input is None:
                logger.error("❌ No se encontró el input de número de cuenta.")
                return

            cuenta_input.clear()
            cuenta_input.send_keys(cuenta)
            logger.info(f"✏️ Cuenta '{cuenta}' ingresada.")

            # Botón Siguiente
            siguiente_btn = self._wait_for_element(By.XPATH, "//button[contains(text(),'Siguiente') or contains(@class,'siguiente')]", timeout=10)
            if siguiente_btn is None:
                # Fallback: buscar cualquier botón con texto "Siguiente"
                siguiente_btn = self._wait_for_element(By.XPATH, "//*[text()='Siguiente']", timeout=5)
            if siguiente_btn:
                siguiente_btn.click()
                logger.info("🖱️ Clic en 'Siguiente'.")
            else:
                logger.warning("⚠️ Botón 'Siguiente' no encontrado, intentando Enter.")
                cuenta_input.send_keys(Keys.RETURN)

            # Esperar que desaparezca el loader "Buscando cuenta"
            self._wait_for_element_disappear(
                By.XPATH,
                "//*[contains(text(),'Buscando cuenta')]",
                timeout=MAX_WAIT
            )

            # Confirmar que cargaron los datos del cliente
            datos = self._wait_for_element(
                By.XPATH,
                "//*[contains(text(),'Datos de la cuenta')]",
                timeout=MAX_WAIT
            )
            if datos:
                logger.info("✅ Datos de la cuenta cargados correctamente.")
                # Hacer clic en la caja roja del paquete (combo resaltado)
                self._click_combo_rojo()
            else:
                logger.error("❌ Timeout esperando datos de la cuenta.")

        except Exception as e:
            logger.error(f"❌ Error en _handle_cuenta: {e}")

    def _click_combo_rojo(self):
        """Hace clic en el checkbox/box del combo marcado en rojo (el paquete del cliente)."""
        try:
            # La caja roja generalmente tiene un estilo inline rojo o clase específica
            # Según la captura: es un div/label con fondo rojo/rosado que contiene el nombre del paquete
            combo_box = self._wait_for_element(
                By.XPATH,
                "//label[contains(@style,'background') and (.//input[@type='checkbox'] or .//input[@type='radio'])]"
                " | //div[contains(@class,'combo') and contains(@style,'red')]"
                " | //div[contains(@class,'combo') and contains(@style,'#')]"
                " | //div[contains(@class,'red') or contains(@class,'danger') or contains(@class,'cancel')]"
                " | //input[@type='checkbox']/following-sibling::*[contains(@style,'background')]",
                timeout=15
            )

            if combo_box is None:
                # Fallback: buscar el primer checkbox visible en el panel
                combo_box = self._wait_for_element(
                    By.CSS_SELECTOR,
                    "input[type='checkbox']",
                    timeout=10
                )

            if combo_box:
                combo_box.click()
                logger.info("🖱️ Clic en caja del combo/paquete.")
            else:
                logger.warning("⚠️ No se encontró la caja del combo rojo. Continuando...")

        except Exception as e:
            logger.error(f"❌ Error en _click_combo_rojo: {e}")

    def _handle_cancelacion(self, tipo: str):
        """Selecciona el radio button de Total o Parcial."""
        try:
            tipo_lower = tipo.strip().lower()
            if tipo_lower == "total":
                xpath = "//input[@type='radio']/following-sibling::*[contains(text(),'Total')] | //label[contains(text(),'Total')]//input | //*[contains(text(),'Total') and self::label]"
            else:
                xpath = "//input[@type='radio']/following-sibling::*[contains(text(),'Parcial')] | //label[contains(text(),'Parcial')]//input | //*[contains(text(),'Parcial') and self::label]"

            radio = self._wait_for_element(By.XPATH, xpath, timeout=20)
            if radio is None:
                # Fallback directo por texto
                radio = self._wait_for_element(
                    By.XPATH,
                    f"//*[self::label or self::span][normalize-space(text())='{tipo.capitalize()}']",
                    timeout=10
                )
            if radio:
                radio.click()
                logger.info(f"✅ Cancelación '{tipo}' seleccionada.")
            else:
                logger.error(f"❌ No se encontró opción de cancelación '{tipo}'.")

        except Exception as e:
            logger.error(f"❌ Error en _handle_cancelacion: {e}")

    def _handle_motivo(self, motivo: str):
        """Hace clic en el motivo de cancelación que coincida con el texto."""
        try:
            motivo_strip = motivo.strip()
            # Buscar el elemento que contenga el texto del motivo en la lista
            xpath = (
                f"//*[contains(normalize-space(text()),'{motivo_strip}')]"
                f" | //td[contains(normalize-space(text()),'{motivo_strip}')]"
                f" | //li[contains(normalize-space(text()),'{motivo_strip}')]"
                f" | //div[contains(normalize-space(text()),'{motivo_strip}') and not(./*[contains(normalize-space(text()),'{motivo_strip}')])]"
            )
            el = self._wait_for_element(By.XPATH, xpath, timeout=20)
            if el:
                el.click()
                logger.info(f"✅ Motivo '{motivo_strip}' seleccionado.")
            else:
                logger.error(f"❌ No se encontró el motivo '{motivo_strip}' en la lista.")

        except Exception as e:
            logger.error(f"❌ Error en _handle_motivo: {e}")

    def _return_to_home(self):
        """Regresa a la pantalla de búsqueda de cuenta para la siguiente llamada."""
        try:
            self.driver.get(f"{BASE_URL}/home")
            self._wait_for_element(
                By.CSS_SELECTOR,
                "input[placeholder*='cuenta'], input[placeholder*='Cuenta'], input[placeholder*='Número']",
                timeout=30
            )
            logger.info("🏠 Regresó a pantalla de búsqueda de cuenta.")
        except Exception as e:
            logger.error(f"❌ Error al regresar a home: {e}")

    # ------------------------------------------------------------------
    # Utilidades de espera (sin sleep fijos — while + poll)
    # ------------------------------------------------------------------
    def _wait_for_element(self, by: str, selector: str, timeout: int = MAX_WAIT):
        """
        Espera hasta que el elemento exista y sea visible en el DOM.
        Retorna el elemento o None si se agota el timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                el = self.driver.find_element(by, selector)
                if el.is_displayed():
                    return el
            except (NoSuchElementException, WebDriverException):
                pass
            time.sleep(POLL_INTERVAL)
        logger.warning(f"⏰ Timeout ({timeout}s) esperando: [{by}] '{selector}'")
        return None

    def _wait_for_element_disappear(self, by: str, selector: str, timeout: int = MAX_WAIT):
        """
        Espera hasta que el elemento desaparezca del DOM o deje de ser visible.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                el = self.driver.find_element(by, selector)
                if not el.is_displayed():
                    return True
            except (NoSuchElementException, WebDriverException):
                return True  # El elemento ya no existe
            time.sleep(POLL_INTERVAL)
        logger.warning(f"⏰ Timeout ({timeout}s) esperando que desaparezca: '{selector}'")
        return False

    def _wait_for_signal(self, filename: str, timeout: int = MAX_WAIT) -> str | None:
        """
        Espera hasta que aparezca el archivo de señal en SIGNALS_DIR.
        Retorna el contenido del archivo (sin espacios) o None si hay timeout.
        """
        signal_path = SIGNALS_DIR / filename
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop_evt.is_set():
                return None
            if signal_path.exists():
                try:
                    content = signal_path.read_text(encoding="utf-8").strip()
                    signal_path.unlink()  # Consumir la señal
                    return content if content else None
                except Exception as e:
                    logger.error(f"Error leyendo señal {filename}: {e}")
            time.sleep(POLL_INTERVAL)
        logger.warning(f"⏰ Timeout ({timeout}s) esperando señal '{filename}'")
        return None

    def _read_signal(self, filename: str) -> str | None:
        """Lee y consume una señal si existe ahora mismo (sin esperar)."""
        signal_path = SIGNALS_DIR / filename
        if signal_path.exists():
            try:
                content = signal_path.read_text(encoding="utf-8").strip()
                signal_path.unlink()
                return content if content else None
            except Exception:
                pass
        return None

    def _clear_signals(self):
        """Elimina todas las señales pendientes al iniciar."""
        for f in SIGNALS_DIR.glob("*.txt"):
            try:
                f.unlink()
            except Exception:
                pass
        logger.info("🧹 Señales anteriores limpiadas.")


# ---------------------------------------------------------------------------
# Entry point — también sirve para prueba manual
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="RPA Retención izzi")
    parser.add_argument("--test", action="store_true", help="Modo test: browser visible + logs detallados")
    parser.add_argument("--headless", action="store_true", help="Ejecutar sin ventana de navegador")
    parser.add_argument("--setup", action="store_true", help="Modo configuración: abre Chrome persistente y pausa para configuraciones manuales")
    args = parser.parse_args()

    # Si es modo setup, no debe ser headless
    headless = args.headless and not args.test and not args.setup
    rpa = RetencionRPA(headless=headless)

    if args.setup:
        logger.info("⚙️ Iniciando modo configuración (setup)...")
        rpa._init_driver()
        # Intentar ir a la tienda de Chrome por comodidad
        try:
            store_url = "https://chromewebstore.google.com/detail/rpa-extension/ccilojpjnmepojkjkdpohdkbjpkfoojd"
            rpa.driver.get(store_url)
        except Exception:
            try:
                rpa.driver.get(LOGIN_URL)
            except Exception:
                pass
        
        print("\n" + "="*80)
        print(" ⚙️  MODO CONFIGURACIÓN ACTIVO (SETUP)")
        print(" Chrome se ha abierto con tu perfil persistente.")
        print(" Realiza las siguientes tareas manualmente en la ventana de Chrome:")
        print("   1. Instala la extensión si es necesario (puedes arrastrar el archivo .crx).")
        print("   2. Inicia sesión en el portal si deseas dejar guardadas las credenciales/sesión.")
        print("="*80 + "\n")
        input(" Presiona [ENTER] aquí en la consola cuando hayas terminado para cerrar Chrome...")
        rpa.stop()
        logger.info("⚙️ Perfil persistente configurado con éxito.")
        return

    try:
        rpa.start()
        logger.info("🟢 RPA activo. Presiona Ctrl+C para detener.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🔴 Interrupción del usuario.")
    finally:
        rpa.stop()


if __name__ == "__main__":
    main()
