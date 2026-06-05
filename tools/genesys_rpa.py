"""
RPA de Automatización para Genesys Workspace Desktop Edition (WDE)
==================================================================
Utiliza la interfaz nativa Windows UI Automation (sin imágenes)
para realizar el inicio de sesión de forma estable y robusta.

Requerimientos:
  py -3.12 -m pip install pywinauto

Uso:
  # Imprimir la estructura interna de la ventana para identificar controles
  py -3.12 tools/genesys_rpa.py --debug
  
  # Ejecutar inicio de sesión
  py -3.12 tools/genesys_rpa.py --username "tu_usuario" --password "tu_clave"
"""

import sys
import time
import logging
import argparse
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError

# Configuración de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - GenesysRPA - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("GenesysRPA")

# Configuración por defecto (modifica según tus necesidades o pásalas por argumento)
DEFAULT_EXE_PATH = r"C:\Program Files (x86)\GCTI\Workspace Desktop Edition\InteractionWorkspace.exe"

class GenesysRPA:
    def __init__(self, exe_path=DEFAULT_EXE_PATH):
        self.exe_path = exe_path
        self.app = None
        self.main_window = None

    def conectar_o_iniciar(self) -> bool:
        """Se conecta a una instancia abierta de Genesys o inicia una nueva."""
        try:
            logger.info("🔗 Intentando conectar a una instancia existente de Genesys WDE...")
            # Intentar conectarse por nombre de proceso
            self.app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=5)
            logger.info("✅ Conexión exitosa a la instancia activa.")
            return True
        except Exception:
            logger.info("🚀 No se encontró Genesys abierto. Iniciando aplicación...")
            try:
                self.app = Application(backend="uia").start(self.exe_path)
                logger.info("✅ Aplicación iniciada.")
                return True
            except Exception as e:
                logger.error(f"❌ Error al iniciar Genesys en '{self.exe_path}': {e}")
                return False

    def obtener_ventana_login(self, timeout=30):
        """Busca y espera a que la ventana de login esté visible."""
        logger.info("⏳ Esperando a que la ventana de inicio de sesión esté visible...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Genesys suele tener ventanas con títulos como "Workspace" o "Login"
                # Buscamos de forma flexible por expresiones regulares
                windows = self.app.windows()
                for w in windows:
                    title = w.texts()[0] if w.texts() else ""
                    # Verificar si es la ventana de login/Workspace principal
                    if "workspace" in title.lower() or "login" in title.lower() or "sesión" in title.lower():
                        if w.is_visible():
                            logger.info(f"🎯 Ventana encontrada: '{title}'")
                            self.main_window = w
                            return w
                time.sleep(1)
            except Exception:
                time.sleep(1)
        logger.error("❌ No se encontró la ventana de inicio de sesión dentro del tiempo límite.")
        return None

    def debug_imprimir_controles(self):
        """
        Imprime en consola todos los controles visibles en la ventana.
        Usa esto para identificar el 'auto_id' (AutomationId) o 'title' (Name) de los campos.
        """
        if not self.main_window:
            logger.error("No hay una ventana seleccionada para imprimir controles.")
            return
        
        logger.info("🔍 Analizando árbol de elementos (esto puede tomar unos segundos)...")
        print("\n" + "="*80)
        print(" ESTRUCTURA INTERNA DE CONTROLES (IDENTIFICADORES)")
        print("="*80)
        # print_control_identifiers() muestra toda la jerarquía de botones, campos de texto, etc.
        self.main_window.print_control_identifiers()
        print("="*80 + "\n")

    def login(self, username, password, place=None) -> bool:
        """
        Realiza el llenado de credenciales e inicia sesión.
        Ajusta los 'auto_id' o 'title' de acuerdo a los resultados del modo --debug.
        """
        if not self.main_window:
            logger.error("No se puede iniciar sesión: Ventana no encontrada.")
            return False

        try:
            logger.info("✏️ Escribiendo credenciales...")
            
            # --- 1. Campo de Usuario ---
            # Intentar por AutomationId típico de Genesys, si no por tipo de control y orden
            try:
                # Ejemplo típico de UIA: child_window por auto_id o title
                user_field = self.main_window.child_window(auto_id="tbUsername", control_type="Edit")
                user_field.set_text(username)
            except ElementNotFoundError:
                # Fallback: buscar el primer Edit visible
                logger.warning("No se halló auto_id='tbUsername'. Usando primer control de tipo texto...")
                self.main_window.child_window(control_type="Edit").set_text(username)

            # --- 2. Campo de Contraseña ---
            try:
                pass_field = self.main_window.child_window(auto_id="pbPassword", control_type="Edit")
                pass_field.set_text(password)
            except ElementNotFoundError:
                # Fallback: buscar el segundo Edit visible
                logger.warning("No se halló auto_id='pbPassword'. Usando segundo control de tipo texto...")
                # Generalmente el segundo Edit en el login es la contraseña
                edits = self.main_window.children(control_type="Edit")
                if len(edits) > 1:
                    edits[1].set_text(password)
                else:
                    logger.error("No se localizó el campo de contraseña.")
                    return False

            # --- 3. Campo de Place / Extensión / Posición (opcional) ---
            if place:
                try:
                    place_field = self.main_window.child_window(auto_id="tbPlace", control_type="Edit")
                    place_field.set_text(place)
                except ElementNotFoundError:
                    # Si hay un tercer campo de texto, escribir el place
                    edits = self.main_window.children(control_type="Edit")
                    if len(edits) > 2:
                        edits[2].set_text(place)

            time.sleep(1)

            # --- 4. Clic en el Botón Login / Aceptar ---
            logger.info("🖱️ Dando clic en botón de Login...")
            try:
                # Buscar botón por su texto visible (Name en UIA)
                login_btn = self.main_window.child_window(title="Iniciar sesión", control_type="Button")
                login_btn.click()
            except ElementNotFoundError:
                try:
                    # Intentar en inglés
                    login_btn = self.main_window.child_window(title="Log In", control_type="Button")
                    login_btn.click()
                except ElementNotFoundError:
                    # Fallback por auto_id o clase de botón
                    logger.error("No se localizó el botón de inicio de sesión.")
                    return False

            logger.info("🚀 Login ejecutado con éxito.")
            return True

        except Exception as e:
            logger.error(f"❌ Error durante el proceso de login: {e}")
            return False

    def login_simple(self) -> bool:
        """
        Realiza el inicio de sesión simple cuando las credenciales ya están guardadas:
        Asegura el foco de la ventana de login y envía la tecla 'ENTER'.
        """
        if not self.main_window:
            logger.error("No se puede iniciar sesión: Ventana no encontrada.")
            return False

        try:
            logger.info("🎯 Enfocando la ventana de Genesys WDE...")
            self.main_window.set_focus()
            time.sleep(0.5)
            logger.info("⌨️ Enviando tecla ENTER...")
            self.main_window.type_keys("{ENTER}")
            logger.info("🚀 Login simple enviado.")
            return True
        except Exception as e:
            logger.error(f"❌ Error al enviar ENTER: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Genesys WDE RPA Client")
    parser.add_argument("--exe", type=str, default=DEFAULT_EXE_PATH, help="Ruta al ejecutable de Genesys")
    parser.add_argument("--username", type=str, help="Nombre de usuario")
    parser.add_argument("--password", type=str, help="Contraseña")
    parser.add_argument("--place", type=str, help="Place / Extensión (opcional)")
    parser.add_argument("--debug", action="store_true", help="Analizar y mostrar los controles de la ventana activa")
    args = parser.parse_args()

    rpa = GenesysRPA(exe_path=args.exe)
    
    if not rpa.conectar_o_iniciar():
        sys.exit(1)

    window = rpa.obtener_ventana_login()
    if not window:
        sys.exit(1)

    if args.debug:
        rpa.debug_imprimir_controles()
        return

    # Si se especifican credenciales, usarlas para escribir y loguearse.
    # De lo contrario, proceder con el login simple de solo presionar ENTER.
    if args.username and args.password:
        rpa.login(args.username, args.password, args.place)
    else:
        logger.info("ℹ️ No se pasaron credenciales. Iniciando sesión simple (ENTER)...")
        rpa.login_simple()

if __name__ == "__main__":
    main()
