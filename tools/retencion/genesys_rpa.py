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
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            logger.info("🔗 Intentando conectar a Genesys WDE por proceso...")
            # Conectar por ejecutable es mucho más rápido y evita bloqueos de UIAutomation al enumerar escritorio
            self.app = Application(backend="uia").connect(path="InteractionWorkspace.exe", timeout=2)
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

    def is_in_call(self) -> bool:
        """Verifica si hay una llamada conectada leyendo la interfaz del Workspace."""
        logger.info(f"[DEBUG] [is_in_call] 1. Entrando a la función is_in_call. Archivo: {__file__}")
        try:
            import pythoncom
            logger.info("[DEBUG] [is_in_call] 2. Ejecutando CoInitialize...")
            pythoncom.CoInitialize()
            
            logger.info("[DEBUG] [is_in_call] 3. Intentando conectar directamente por título '.*Workspace.*'...")
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=2)
            logger.info("[DEBUG] [is_in_call] 4. Conectado exitosamente. Obteniendo objeto ventana...")
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                logger.info("[DEBUG] [is_in_call] 5a. La ventana con título 'Workspace' no existe en el sistema.")
                return False
                
            logger.info("[DEBUG] [is_in_call] 5b. Ventana encontrada. Buscando controles...")
                
            logger.info("[DEBUG] Buscando botones de llamada activa en la ventana Genesys...")
            # Realizar una búsqueda única por expresión regular para ahorrar tiempo y evitar timeouts por concurrencia
            try:
                btn = main_window.child_window(title_re=".*(Instant call Transfer|End The Call|End Call).*", control_type="Button")
                if btn.exists(timeout=0.5):
                    logger.info("[DEBUG] Botón de interacción activa encontrado.")
                    return True
            except Exception as ex:
                logger.info(f"[DEBUG] Error buscando botón de interacción activa: {ex}")
                
        except Exception as e:
            logger.info(f"[DEBUG] Excepción general en is_in_call: {e}")
            
        return False

    def get_active_call_data(self) -> dict:
        """Extrae el número de teléfono de la llamada activa."""
        data = {"phone_number": "", "CUENTA": "", "lead_id": "", "first_name": "", "last_name": ""}
        
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=1)
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                return data
                
            import re
            # Extraer de forma rápida solo el elemento que parece un teléfono (soporta de 10 a 12 dígitos)
            for d in main_window.descendants():
                try:
                    t = d.window_text()
                    if t:
                        match = re.search(r"\b\d{10,12}\b", t)
                        if match:
                            data["phone_number"] = match.group(0)
                            data["lead_id"] = match.group(0) 
                            break
                except Exception:
                    pass
                    
        except Exception as e:
            logger.debug(f"Error extrayendo datos de llamada en Genesys: {e}")
            
        return data

    def get_lead_id_fast(self) -> str:
        """Fallback ultra rápido para el lead_id usado por agent_core.py."""
        return self.get_active_call_data().get("lead_id", "")

    def transfer_call_genesys(self, destination: str) -> bool:
        """
        Realiza una transferencia de llamada en Genesys Workspace.
        Destinos posibles:
          - 'soporte' / 'tecnico': 75065
          - 'servicios': 91305
          - 'izzi movil': 75058
        """
        dest_lower = destination.strip().lower()
        
        if any(x in dest_lower for x in ("soporte", "tecnico", "técnico", "falla")):
            number = "75065"
        elif any(x in dest_lower for x in ("servicio", "servicios", "comercial")):
            number = "91305"
        elif any(x in dest_lower for x in ("movil", "móvil", "celular")):
            number = "75058"
        else:
            logger.error(f"❌ Destino de transferencia no reconocido: {destination}")
            return False
            
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=1)
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                return False
                
            # El título en la UI de Genesys puede terminar en un espacio "Instant call Transfer " o "Instant call Transfer"
            btn = main_window.child_window(title="Instant call Transfer ", control_type="Button")
            if not btn.exists(timeout=0.5):
                btn = main_window.child_window(title="Instant call Transfer", control_type="Button")
                
            if btn.exists(timeout=0.5):
                main_window.set_focus()
                btn.click()
                import time
                time.sleep(1.0) # Esperar a que el popup/campo de búsqueda aparezca y tome foco
                
                # Enviar el número y dar enter
                main_window.type_keys(f"{number}{{ENTER}}", protect_first=True)
                logger.info(f"✅ Transferencia de llamada a {destination} ({number}) enviada en Genesys WDE.")
                return True
            else:
                logger.error("❌ No se encontró el botón de transferencia 'Instant call Transfer'.")
        except Exception as e:
            logger.error(f"❌ Error durante transferencia en Genesys: {e}")
        return False

    def is_done_button_visible(self) -> bool:
        """Verifica si el botón 'Done Ctrl+E' está visible en la ventana del Workspace."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=1)
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                return False
                
            # Intentar buscar por múltiples nombres comunes o AutomationIds
            for title in ("Done Ctrl+E", "Done", "Done ", "Done (Ctrl+E)"):
                try:
                    btn = main_window.child_window(title=title, control_type="Button")
                    if btn.exists(timeout=0.1):
                        visible = False
                        enabled = False
                        try:
                            visible = btn.is_visible()
                            enabled = btn.is_enabled()
                        except Exception:
                            pass
                        
                        if visible and enabled:
                            return True
                        else:
                            logger.debug(f"Botón Done por título '{title}' existe pero visible={visible}, habilitado={enabled}")
                except Exception:
                    pass
            for auto_id in ("DoneButton", "Done", "InteractionDoneButton"):
                try:
                    btn = main_window.child_window(auto_id=auto_id, control_type="Button")
                    if btn.exists(timeout=0.1):
                        visible = False
                        enabled = False
                        try:
                            visible = btn.is_visible()
                            enabled = btn.is_enabled()
                        except Exception:
                            pass
                        
                        if visible and enabled:
                            return True
                        else:
                            logger.debug(f"Botón Done por auto_id '{auto_id}' existe pero visible={visible}, habilitado={enabled}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Error verificando botón Done en Genesys: {e}")
        return False

    def click_done_button(self) -> bool:
        """Hace clic en el botón 'Done Ctrl+E'."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=1)
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                return False
                
            for title in ("Done Ctrl+E", "Done", "Done ", "Done (Ctrl+E)"):
                try:
                    btn = main_window.child_window(title=title, control_type="Button")
                    if btn.exists(timeout=0.2):
                        visible = False
                        enabled = False
                        try:
                            visible = btn.is_visible()
                            enabled = btn.is_enabled()
                        except Exception:
                            pass
                        
                        if visible and enabled:
                            btn.click()
                            logger.info(f"🖱️ Clic en botón Done ('{title}') realizado con éxito.")
                            return True
                except Exception:
                    pass
            for auto_id in ("DoneButton", "Done", "InteractionDoneButton"):
                try:
                    btn = main_window.child_window(auto_id=auto_id, control_type="Button")
                    if btn.exists(timeout=0.2):
                        visible = False
                        enabled = False
                        try:
                            visible = btn.is_visible()
                            enabled = btn.is_enabled()
                        except Exception:
                            pass
                        
                        if visible and enabled:
                            btn.click()
                            logger.info(f"🖱️ Clic en botón Done (auto_id: '{auto_id}') realizado con éxito.")
                            return True
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"❌ Error al hacer clic en Done Ctrl+E: {e}")
        return False

    def click_end_call_button(self) -> bool:
        """Hace clic en el botón 'End The Call' para colgar desde el agente."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            
            app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=1)
            main_window = app.window(title_re=".*Workspace.*")
            
            if not main_window.exists(timeout=0.5):
                return False
                
            btn = main_window.child_window(title="End The Call", control_type="Button")
            if not btn.exists(timeout=0.5):
                # Fallback alternativo "End Call"
                btn = main_window.child_window(title="End Call", control_type="Button")
                
            if btn.exists(timeout=0.5):
                btn.click()
                logger.info("🖱️ Clic en botón 'End The Call' realizado con éxito.")
                return True
        except Exception as e:
            logger.error(f"❌ Error al hacer clic en End The Call: {e}")
        return False

    def is_call_hungup(self) -> bool:
        """Determina si la llamada colgó comprobando si el botón Done está visible."""
        return self.is_done_button_visible()


def main():
    parser = argparse.ArgumentParser(description="Genesys WDE RPA Client")
    parser.add_argument("--exe", type=str, default=DEFAULT_EXE_PATH, help="Ruta al ejecutable de Genesys")
    parser.add_argument("--username", type=str, help="Nombre de usuario")
    parser.add_argument("--password", type=str, help="Contraseña")
    parser.add_argument("--place", type=str, help="Place / Extensión (opcional)")
    parser.add_argument("--debug", action="store_true", help="Analizar y mostrar los controles de la ventana activa")
    
    # Argumentos para subproceso
    parser.add_argument("--is-in-call", action="store_true", help="Verifica si hay llamada activa")
    parser.add_argument("--get-call-data", action="store_true", help="Extrae datos de llamada activa")
    parser.add_argument("--is-done-visible", action="store_true", help="Verifica si el botón Done está visible")
    parser.add_argument("--click-done", action="store_true", help="Haz clic en Done")
    parser.add_argument("--click-end", action="store_true", help="Haz clic en End Call / Colgar")
    parser.add_argument("--transfer", type=str, help="Transfiere la llamada al destino indicado")
    parser.add_argument("--debug-window", action="store_true", help="Analizar y mostrar los controles de la ventana activa directamente por título")
    
    args = parser.parse_args()

    # Procesar comando debug-window directamente
    if args.debug_window:
        import pythoncom
        pythoncom.CoInitialize()
        app = Application(backend="uia").connect(title_re=".*Workspace.*", timeout=2)
        main_window = app.window(title_re=".*Workspace.*")
        if main_window.exists(timeout=0.5):
            main_window.print_control_identifiers()
        else:
            print("No se encontró la ventana del Workspace.")
        return

    rpa = GenesysRPA(exe_path=args.exe)
    
    # Procesar comandos rápidos del subproceso directamente sin requerir ventana de login
    if args.is_in_call:
        print("TRUE" if rpa.is_in_call() else "FALSE")
        return
    elif args.get_call_data:
        import json
        data = rpa.get_active_call_data()
        print(json.dumps(data))
        return
    elif args.is_done_visible:
        print("TRUE" if rpa.is_done_button_visible() else "FALSE")
        return
    elif args.click_done:
        print("TRUE" if rpa.click_done_button() else "FALSE")
        return
    elif args.click_end:
        print("TRUE" if rpa.click_end_call_button() else "FALSE")
        return
    elif args.transfer:
        print("TRUE" if rpa.transfer_call_genesys(args.transfer) else "FALSE")
        return

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
