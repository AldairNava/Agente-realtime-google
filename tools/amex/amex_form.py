"""
AMEX Form Automation — Llenado automático del formulario y APIs de Backend
=============================================================================
Usa Selenium en segundo plano para llenar la solicitud y se sincroniza con
Gemini mediante archivos de texto. Luego consume las APIs del cliente.
"""

import os
import time
import json
import logging
import threading
import tempfile
import shutil
import requests
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger("AMEXForm")

TARJETAS_URLS = {
    "amex_personal": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/la-tarjeta?sourcecode=A0000HWUEA&cpid=100632170&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoRCPGreen&utm_content=RCPGreen",
    "amex_aeromexico": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/la-tarjeta-aeromexico?sourcecode=A0000HWUFF&cpid=100632225&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoRCPAeromexicoGreen&utm_content=RCPAeromexicoGreen",
    "platinum_credit": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/the-platinum-credit-card?sourcecode=A0000HWUHH&cpid=100632150&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoGRCCPlatinum&utm_content=GRCCPlatinum",
    "gold_card": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/the-gold-card?sourcecode=A0000HWUE3&cpid=100632189&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesBAULead2BusinessAsistidoRCPGold&utm_content=RCPGold",
    "gold_aeromexico": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/the-gold-card-aeromexico?sourcecode=A0000HWUH0&cpid=100632284&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoRCPAeromexicoGold&utm_content=RCPAeromexicoGold",
    "platinum_aeromexico": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/the-platinum-card-aeromexico?sourcecode=A0000HWUEW&cpid=100632302&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoRCPAeromexicoPlatinum&utm_content=RCPAeromexicoPlatinum",
    "platinum_card": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/clusters/the-platinum-card?sourcecode=A0000HWUH9&cpid=100632207&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesLTOLead2BusinessAsistidoRCPPlatinum&utm_content=RCPPlatinum",
    "business_gold": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/affiliates-tiaxa/the-gold-card-sbs?sourcecode=A0000HWU3J&cpid=100632326&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesBAULead2BusinessAsistidoRCPSBSGold&utm_content=RCPSBSGold",
    "business_platinum": "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/beneficios/affiliates-tiaxa/the-business-platinum-card-sbs?sourcecode=A0000HWU3R&cpid=100632347&utm_source=lead2Business&utm_medium=Asistido&utm_campaign=AffiliatesBAULead2BusinessAsistidoRCPSBSPlatinum&utm_content=RCPSBSPlatinum"
}

CAMPOS_REQUERIDOS = {
    "nombre": "Nombre(s)",
    "apellido_paterno": "Apellido paterno",
    "apellido_materno": "Apellido materno",
    "dia_nacimiento": "Día",
    "mes_nacimiento": "Mes",
    "anio_nacimiento": "Año"
}

# Configuraciones de API (Backend)
API_BUSCAR_LEAD = "http://192.168.50.33/api/Amex_ventas/buscarLeadAmex"
API_GUARDAR_VENTA = "http://192.168.50.33/api/Amex_ventas/guardarVenta"


class AMEXFormHandler:
    def __init__(self, client_phone="", vicidial_user="cyber_agente", lead_id=""):
        self._datos = {}
        self.client_phone = client_phone
        self.vicidial_user = vicidial_user
        self.lead_id = lead_id
        self.driver = None
        self.sync_dir = os.path.join(os.path.dirname(__file__), 'amex_sync')
        os.makedirs(self.sync_dir, exist_ok=True)

    # ═══════════════════════════════════════════
    #  TOOLS EXPUESTAS A GEMINI
    # ═══════════════════════════════════════════

    def guardar_dato_cliente(self, campo: str, valor: str) -> str:
        """
        Guarda un dato del cliente ANTES de lanzar el formulario.
        Args:
            campo: Nombre del campo exacto. Opciones OBLIGATORIAS:
                   - nombre
                   - apellido_paterno
                   - apellido_materno
                   - dia_nacimiento (solo el número)
                   - mes_nacimiento (nombre del mes)
                   - anio_nacimiento (4 dígitos)
            valor: El valor correspondiente
        """
        campo = campo.strip().lower()
        if campo in ("tiene_tdc", "tiene_auto", "tiene_hipoteca"):
            valor = "si" if valor.strip().lower() in ("sí", "si", "yes", "s", "1", "true") else "no"
        self._datos[campo] = valor.strip()
        logger.info(f"📝 [AMEX] Dato guardado: {campo} = '{valor.strip()}'")
        return f"Dato '{campo}' guardado."

    def ver_datos_capturados(self) -> str:
        """Muestra los datos iniciales capturados."""
        return str(self._datos)

    def iniciar_llenado_formulario_amex(self, id_tarjeta: str) -> str:
        """
        Llama a esta herramienta cuando el cliente acepte la tarjeta. 
        Inicia el llenado del formulario en segundo plano. Luego te pedirá por sistema 
        confirmar el RFC y datos faltantes.
        """
        id_tarjeta = id_tarjeta.strip()
        if id_tarjeta not in TARJETAS_URLS:
            return f"Error: ID inválido '{id_tarjeta}'."

        url = TARJETAS_URLS[id_tarjeta]
        
        # Validar campos básicos
        faltantes = [c for c in CAMPOS_REQUERIDOS if c not in self._datos]
        if faltantes:
            return f"Error: Faltan datos básicos para iniciar: {', '.join(faltantes)}. Captúralos primero."

        # Terminar driver activo si existe (cambio a Persona Moral / Business)
        if getattr(self, 'driver', None):
            try:
                self.driver.quit()
                logger.info("🛑 [AMEX] Navegador anterior cerrado para iniciar nuevo formulario.")
            except: pass
            self.driver = None
            
        # Limpiar archivos de sincronización anteriores siempre al iniciar
        for f in os.listdir(self.sync_dir):
            if f.endswith('.txt'):
                try: os.remove(os.path.join(self.sync_dir, f))
                except: pass

        logger.info(f"🚀 [AMEX] Iniciando proceso asíncrono para {id_tarjeta}...")
        threading.Thread(target=self._run_selenium_flow, args=(url,), daemon=True).start()
        
        return "El formulario se está llenando en segundo plano. Continúa la plática con el cliente y espera instrucciones del [SISTEMA] para confirmar el RFC u otros datos."

    def confirmar_rfc_amex(self, es_correcto: bool, rfc_corregido: str = "") -> str:
        """
        Usa esto después de preguntarle al cliente si el RFC generado automáticamente es correcto.
        Si es_correcto es True, deja rfc_corregido vacío. 
        Si es False, pon en rfc_corregido el RFC que dictó el cliente.
        """
        logger.info(f"✅ [AMEX] RFC confirmado: {es_correcto}, Corregido: {rfc_corregido}")
        path = os.path.join(self.sync_dir, "rfc_confirmacion.txt")
        with open(path, 'w', encoding='utf-8') as f:
            if es_correcto:
                f.write("true")
            else:
                f.write(rfc_corregido)
        return "Confirmación de RFC enviada al formulario."

    def proveer_dato_faltante_amex(self, campo: str, valor: str) -> str:
        """
        Usa esto cuando el [SISTEMA] te pida un dato faltante (ej. correo, celular).
        Args:
            campo: El campo solicitado.
            valor: La respuesta del cliente.
        """
        if campo in ("tiene_tdc", "tiene_auto", "tiene_hipoteca"):
            valor = "si" if valor.strip().lower() in ("sí", "si", "yes", "s", "1", "true") else "no"
        
        self._datos[campo] = valor
        logger.info(f"✅ [AMEX] Dato faltante provisto: {campo} = {valor}")
        
        path = os.path.join(self.sync_dir, f"{campo}_confirmacion.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(valor)
        return f"Dato {campo} enviado al formulario."

    def obtener_rfc_extraido_amex(self) -> str:
        """
        Llama a esta herramienta cuando el cliente NO se sepa su RFC. 
        Espera a que el formulario en segundo plano se llene y extraiga el RFC autogenerado.
        Devuelve el RFC extraído.
        """
        logger.info("🔍 [AMEX] Herramienta 'obtener_rfc_extraido_amex' invocada. Esperando RFC autogenerado...")
        path = os.path.join(self.sync_dir, "need_rfc.txt")
        start_time = time.time()
        while time.time() - start_time < 120:
            if os.path.exists(path):
                time.sleep(0.2)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        rfc = f.read().strip()
                    os.remove(path)
                    logger.info(f"✅ [AMEX] RFC extraído exitosamente de need_rfc.txt: {rfc}")
                    return f"El RFC generado automáticamente por el sistema es: {rfc}. Por favor, confírmalo con el cliente."
                except Exception as e:
                    logger.warning(f"Error leyendo need_rfc.txt: {e}")
            time.sleep(1)
        logger.error("❌ [AMEX] Tiempo de espera agotado buscando need_rfc.txt")
        return "Error: No se pudo obtener el RFC automáticamente. Por favor pídalo manualmente o proceda a reprogramar."

    def _guardar_informacion_llamadas(self):
        try:
            # Directorio src/llamadas
            src_dir = os.path.dirname(os.path.dirname(__file__)) # tools/.. -> root
            llamadas_dir = os.path.join(src_dir, 'src', 'llamadas')
            os.makedirs(llamadas_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            nombre_cliente = f"{self._datos.get('nombre', '')}_{self._datos.get('apellido_paterno', '')}".strip().replace(" ", "_")
            phone = self.client_phone or self._datos.get('celular', 'desconocido')
            lead_id = self.lead_id or "sin_lead_id"
            filename = f"venta_{lead_id}_{nombre_cliente}_{timestamp}.txt"
            filepath = os.path.join(llamadas_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._datos, f, ensure_ascii=False, indent=4)
            logger.info(f"💾 [AMEX Async] Simulación de envío: Datos guardados en {filepath}")
        except Exception as e:
            logger.error(f"❌ [AMEX Async] Error guardando información en llamadas: {e}")


    # ═══════════════════════════════════════════
    #  FLUJO ASÍNCRONO DE SELENIUM Y APIS
    # ═══════════════════════════════════════════

    def _run_selenium_flow(self, form_url: str):
        tmp_user_data = tempfile.mkdtemp(prefix="amex_chrome_")
        driver = None

        try:
            chrome_options = Options()
            chrome_options.add_argument(f"--user-data-dir={tmp_user_data}")
            # chrome_options.add_argument("--headless=new")  # Desactivado a petición del usuario
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--ignore-certificate-errors")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            driver = webdriver.Chrome(options=chrome_options)
            self.driver = driver
            driver.maximize_window()
            driver.set_page_load_timeout(30)
            wait = WebDriverWait(driver, 15)

            logger.info(f"🌐 [AMEX Async] Cargando: {form_url}")
            driver.get(form_url)
            time.sleep(3)

            # 1. Nombres
            for key, selectors in [
                ("nombre", ["//input[@id='name']", "//input[contains(@aria-label, 'Nombre')]"]),
                ("apellido_paterno", ["//input[@id='fathersurname']", "//input[contains(@aria-label, 'paterno')]"]),
                ("apellido_materno", ["//input[@id='mothersurname']", "//input[contains(@aria-label, 'materno')]"])
            ]:
                el = self._find_input_field(driver, wait, selectors)
                if el: self._fill_text_field(driver, el, self._datos.get(key, ""))

            # 2. Fecha de Nacimiento
            self._select_date_of_birth(driver, wait)

            # 3. Esperar que se auto-genere el RFC
            time.sleep(2)
            rfc_el = self._find_input_field(driver, wait, ["//input[@id='vat']", "//input[@name='vat']", "//input[contains(@aria-label, 'RFC')]", "//input[@id='rfc']"])
            
            # Buscar si el RFC está dividido (vata, vatb, vatc)
            vata_el = self._find_input_field(driver, wait, ["//input[@id='vata']"])
            if vata_el:
                vatb_el = self._find_input_field(driver, wait, ["//input[@id='vatb']"])
                vatc_el = self._find_input_field(driver, wait, ["//input[@id='vatc']"])
                rfc_generado = (vata_el.get_attribute('value') or "") + (vatb_el.get_attribute('value') or "") + (vatc_el.get_attribute('value') or "") if vatb_el and vatc_el else ""
            else:
                rfc_generado = rfc_el.get_attribute('value') if rfc_el else ""
            
            # Pedir confirmación a la IA
            self._request_sync_data("rfc", rfc_generado)
            
            # Esperar respuesta del RFC
            rfc_resp = self._wait_for_sync_data("rfc_confirmacion.txt")
            rfc_a_escribir = rfc_resp if rfc_resp != "true" else rfc_generado
            self._datos['rfc'] = rfc_a_escribir
            
            if vata_el and len(rfc_a_escribir) >= 10:
                vatb_el = self._find_input_field(driver, wait, ["//input[@id='vatb']"])
                vatc_el = self._find_input_field(driver, wait, ["//input[@id='vatc']"])
                
                part_1 = rfc_a_escribir[:4]
                part_2 = rfc_a_escribir[4:10]
                part_3 = rfc_a_escribir[10:]
                
                self._fill_text_field(driver, vata_el, part_1)
                if vatb_el: self._fill_text_field(driver, vatb_el, part_2)
                if vatc_el: self._fill_text_field(driver, vatc_el, part_3)
                logger.info(f"✅ [AMEX Async] RFC dividido y llenado: {part_1} - {part_2} - {part_3}")
            elif rfc_el:
                self._fill_text_field(driver, rfc_el, rfc_a_escribir)

            # Hacer clic en "Mi RFC es correcto"
            try:
                rfc_checkbox = driver.find_element(By.ID, "rfc_valid")
                driver.execute_script("arguments[0].click();", rfc_checkbox)
                logger.info("✅ [AMEX Async] Checkbox rfc_valid clickeado.")
            except Exception as e:
                logger.warning(f"Error clickeando checkbox rfc_valid: {e}")

            # Hacer clic en "Acepto Términos" si existe (ej: business_platinum)
            try:
                terms_checkbox = driver.find_element(By.ID, "terminos_valid")
                driver.execute_script("arguments[0].click();", terms_checkbox)
                logger.info("✅ [AMEX Async] Checkbox terminos_valid clickeado.")
            except Exception as e:
                pass

            # 4. Campos adicionales faltantes
            campos_adicionales = [
                ("email", ["//input[@id='email']", "//input[@type='email']"]),
                ("celular", ["//input[@id='telephone']", "//input[@type='tel']", "//input[@id='mobile']"]),
                ("codigo_postal", ["//input[@id='codigo_postal']", "//input[@name='codigo_postal']", "//input[contains(@aria-label, 'postal')]", "//input[@id='zipcode']"])
            ]

            for clave, selectors in campos_adicionales:
                valor = self._datos.get(clave, "")
                if not valor:
                    self._request_sync_data(clave)
                    valor = self._wait_for_sync_data(f"{clave}_confirmacion.txt")
                    self._datos[clave] = valor
                
                el = self._find_input_field(driver, wait, selectors)
                if el: self._fill_text_field(driver, el, valor)

            # 4.5 Campos corporativos adicionales (Ocupación e Is Client)
            ocupacion_el = self._find_input_field(driver, wait, ["//select[@id='ocupacion']", "//select[@name='ocupacion']"])
            if ocupacion_el:
                valor_ocupacion = self._datos.get("ocupacion", "")
                if not valor_ocupacion:
                    self._request_sync_data("ocupacion")
                    valor_ocupacion = self._wait_for_sync_data("ocupacion_confirmacion.txt")
                    self._datos["ocupacion"] = valor_ocupacion
                
                valor_ocupacion = valor_ocupacion.strip().lower()
                norm_map = {
                    "ejecutivo": "ejecutivo", "contador": "contador", "director": "director_gerente_supervisor",
                    "gerente": "director_gerente_supervisor", "supervisor": "director_gerente_supervisor",
                    "vendedor": "vendedor", "servicio": "servicio_cliente", "cliente": "servicio_cliente",
                    "chofer": "chofer", "abogado": "abogado", "otros": "otros", "otro": "otros"
                }
                val_to_select = "otros"
                for k, v in norm_map.items():
                    if k in valor_ocupacion:
                        val_to_select = v
                        break
                        
                try:
                    s = Select(ocupacion_el)
                    s.select_by_value(val_to_select)
                    logger.info(f"✅ [AMEX Async] Ocupación seleccionada: {val_to_select}")
                except Exception as e:
                    logger.warning(f"Error al seleccionar ocupación: {e}")

            client_select = self._find_input_field(driver, wait, ["//select[@id='is_client']", "//select[@id='cliente_amex']", "//select[@name='is_client']"])
            if client_select:
                es_cliente = self._datos.get("es_cliente_amex", "no").strip().lower()
                val_to_select = "YES" if es_cliente in ("si", "sí", "yes", "true", "1") else "NO"
                try:
                    s = Select(client_select)
                    s.select_by_value(val_to_select)
                    logger.info(f"✅ [AMEX Async] Campo cliente AMEX seleccionado: {val_to_select}")
                except Exception as e:
                    logger.warning(f"Error al seleccionar cliente AMEX: {e}")

            # 5. Radio Buttons (TDC, Auto, Hipoteca)
            for radio_clave in ["tiene_tdc", "tiene_auto", "tiene_hipoteca"]:
                if radio_clave not in self._datos:
                    self._request_sync_data(radio_clave)
                    self._datos[radio_clave] = self._wait_for_sync_data(f"{radio_clave}_confirmacion.txt")
            
            self._select_radio_buttons(driver)

            # 6. Formulario Listo, esperar a que agente cuelgue
            logger.info("✅ [AMEX Async] Formulario totalmente lleno. Avisando a Gemini...")
            with open(os.path.join(self.sync_dir, 'formulario_listo.txt'), 'w', encoding='utf-8') as f:
                f.write("listo")

            # Esperar archivo call_ended.txt
            logger.info("⏳ [AMEX Async] Esperando a que el agente se despida y cuelgue...")
            self._wait_for_sync_data("call_ended.txt")

            # 7. Hacer clic en Enviar - DEJAR COMENTADO A PETICION DEL USUARIO
            logger.info("📤 [AMEX Async] Botón Enviar (SIMULACIÓN). No se enviará a producción.")
            self._guardar_informacion_llamadas()
            
            # enviar_btn = self._find_input_field(driver, wait, ["//button[@id='formSubmit']", "//button[contains(text(), 'Enviar')]", "//input[@type='submit']"])
            # if enviar_btn:
            #     driver.execute_script("arguments[0].scrollIntoView(true);", enviar_btn)
            #     time.sleep(1)
            #     driver.execute_script("arguments[0].click();", enviar_btn)
            #     logger.info("📤 [AMEX Async] Botón Enviar clickeado. Esperando Thank You page...")
            #     time.sleep(5)
            #     current_url = driver.current_url
            #     logger.info(f"🔗 [AMEX Async] URL Resultante: {current_url}")
            #     self._procesar_apis_backend(current_url)

        except Exception as e:
            logger.error(f"❌ [AMEX Async] Error general en hilo: {e}")
        finally:
            if driver:
                try: driver.quit()
                except: pass
            try: shutil.rmtree(tmp_user_data, ignore_errors=True)
            except: pass
            
            # Avisar que terminó para tipificar
            with open(os.path.join(self.sync_dir, 'proceso_finalizado.txt'), 'w', encoding='utf-8') as f:
                f.write("ok")

    # ═══════════════════════════════════════════
    #  HELPERS DEL FLUJO ASÍNCRONO
    # ═══════════════════════════════════════════

    def _request_sync_data(self, campo: str, contenido: str = ""):
        """Escribe un archivo need_campo.txt para que lo recoja el watchdog."""
        path = os.path.join(self.sync_dir, f"need_{campo}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(contenido if contenido else campo)

    def _wait_for_sync_data(self, filename: str) -> str:
        """Bloquea el hilo hasta que aparezca el archivo de confirmación, procesando actualizaciones de otros campos en el camino."""
        path = os.path.join(self.sync_dir, filename)
        while True:
            # 1. Comprobar si hay otros archivos de confirmación en el directorio para campos ya pasados o futuros
            if getattr(self, 'driver', None):
                try:
                    for f in os.listdir(self.sync_dir):
                        if f.endswith("_confirmacion.txt") and f != filename:
                            f_path = os.path.join(self.sync_dir, f)
                            field_name = f.replace("_confirmacion.txt", "")
                            time.sleep(0.1)
                            try:
                                with open(f_path, 'r', encoding='utf-8') as file_obj:
                                    value = file_obj.read().strip()
                                
                                logger.info(f"🔄 [AMEX Sync] Actualización fuera de flujo detectada para campo '{field_name}': {value}")
                                self._actualizar_campo_dinamico(field_name, value)
                                os.remove(f_path)
                            except Exception as update_err:
                                logger.warning(f"Error procesando actualización de {f}: {update_err}")
                except Exception:
                    pass

            # 2. Comprobar si el archivo esperado ha aparecido
            if os.path.exists(path):
                time.sleep(0.2)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = f.read().strip()
                    os.remove(path)
                    return data
                except Exception as e:
                    logger.warning(f"Error leyendo {filename}: {e}")
            time.sleep(1)

    def _actualizar_campo_dinamico(self, campo: str, valor: str):
        if not getattr(self, 'driver', None):
            return
            
        selectors_map = {
            "nombre": ["//input[@id='name']", "//input[contains(@aria-label, 'Nombre')]"],
            "apellido_paterno": ["//input[@id='fathersurname']", "//input[contains(@aria-label, 'paterno')]"],
            "apellido_materno": ["//input[@id='mothersurname']", "//input[contains(@aria-label, 'materno')]"],
            "email": ["//input[@id='email']", "//input[@type='email']"],
            "celular": ["//input[@id='celular']", "//input[@id='mobile']", "//input[@name='mobile']"],
            "codigo_postal": ["//input[@id='zipcode']", "//input[@id='cp']", "//input[@name='zipcode']"],
            "ocupacion": ["//select[@id='ocupacion']", "//select[@name='ocupacion']"],
        }
        
        try:
            if campo == "rfc":
                vata_el = self._find_input_field(self.driver, None, ["//input[@id='vata']"])
                if vata_el and len(valor) >= 10:
                    vatb_el = self._find_input_field(self.driver, None, ["//input[@id='vatb']"])
                    vatc_el = self._find_input_field(self.driver, None, ["//input[@id='vatc']"])
                    part_1 = valor[:4]
                    part_2 = valor[4:10]
                    part_3 = valor[10:]
                    self._fill_text_field(self.driver, vata_el, part_1)
                    if vatb_el: self._fill_text_field(self.driver, vatb_el, part_2)
                    if vatc_el: self._fill_text_field(self.driver, vatc_el, part_3)
                else:
                    rfc_el = self._find_input_field(self.driver, None, ["//input[@id='vat']", "//input[@name='vat']", "//input[@id='rfc']"])
                    if rfc_el:
                        self._fill_text_field(self.driver, rfc_el, valor)
            elif campo == "ocupacion":
                ocupacion_el = self._find_input_field(self.driver, None, selectors_map["ocupacion"])
                if ocupacion_el:
                    valor_ocupacion = valor.strip().lower()
                    norm_map = {
                        "ejecutivo": "ejecutivo", "contador": "contador", "director": "director_gerente_supervisor",
                        "gerente": "director_gerente_supervisor", "supervisor": "director_gerente_supervisor",
                        "vendedor": "vendedor", "servicio": "servicio_cliente", "cliente": "servicio_cliente",
                        "chofer": "chofer", "abogado": "abogado", "otros": "otros", "otro": "otros"
                    }
                    val_to_select = "otros"
                    for k, v in norm_map.items():
                        if k in valor_ocupacion:
                            val_to_select = v
                            break
                    s = Select(ocupacion_el)
                    s.select_by_value(val_to_select)
                    logger.info(f"✅ [AMEX Async] Ocupación actualizada: {val_to_select}")
            elif campo in selectors_map:
                el = self._find_input_field(self.driver, None, selectors_map[campo])
                if el:
                    self._fill_text_field(self.driver, el, valor)
        except Exception as e:
            logger.warning(f"No se pudo actualizar dinámicamente el campo {campo}: {e}")

    def _procesar_apis_backend(self, url_resultante: str):
        """Llama a buscarLeadAmex y guardarVenta usando el teléfono y los datos extraídos."""
        try:
            parsed = urlparse(url_resultante)
            qs = parse_qs(parsed.query)
            l_value = qs.get('l', [''])[0]
            iv_value = qs.get('iv', [''])[0]
            
            logger.info(f"🔍 [AMEX API] Buscando cliente con teléfono: {self.client_phone}")
            
            # 1. Buscar Lead
            lead_data = {"lead_id": "", "list_id": ""}
            if self.client_phone:
                res_buscar = requests.post(API_BUSCAR_LEAD, json={"telefono": self.client_phone}, timeout=10)
                if res_buscar.status_code == 200:
                    data = res_buscar.json()
                    logger.info("✅ [AMEX API] Cliente encontrado.")
                    datos_cliente = data.get("datos", {})
                    lead_data["lead_id"] = datos_cliente.get("lead_id", "")
                    lead_data["list_id"] = datos_cliente.get("list_id", "")
                else:
                    logger.warning(f"⚠️ [AMEX API] Error en buscarLead: {res_buscar.text}")

            # 2. Guardar Venta
            payload_venta = {
                "lead_id": lead_data["lead_id"],
                "list_id": lead_data["list_id"],
                "phone_number": self.client_phone or self._datos.get("celular", ""),
                "first_name": self._datos.get("nombre", ""),
                "last_name": f"{self._datos.get('apellido_paterno', '')} {self._datos.get('apellido_materno', '')}".strip(),
                "email": self._datos.get("email", ""),
                "user": self.vicidial_user,
                "l_parameter": l_value,
                "iv_parameter": iv_value,
                "url_final": url_resultante,
                "datos_completos_formulario": self._datos
            }
            
            logger.info("💾 [AMEX API] Guardando venta en backend...")
            res_guardar = requests.post(API_GUARDAR_VENTA, json=payload_venta, timeout=10)
            if res_guardar.status_code == 200:
                logger.info(f"✅ [AMEX API] Venta guardada: {res_guardar.json()}")
            else:
                logger.error(f"❌ [AMEX API] Error al guardar venta: {res_guardar.text}")

        except Exception as e:
            logger.error(f"❌ [AMEX API] Excepción llamando a APIs: {e}")

    # ═══════════════════════════════════════════
    #  HELPERS DE SELENIUM (Navegación)
    # ═══════════════════════════════════════════

    def _find_input_field(self, driver, wait, selectors):
        for selector in selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed(): return element
            except: continue
        return None

    def _fill_text_field(self, driver, element, value):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            element.click()
            element.clear()
            element.send_keys(value)
            
            # Intento JS por si es React/Angular
            driver.execute_script(
                """
                var el = arguments[0]; var value = arguments[1];
                try {
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, value);
                } catch(e) {}
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                """, element, value
            )
            logger.info(f"✅ [AMEX Async] Campo llenado con éxito: {value}")
        except Exception as e:
            logger.warning(f"Error llenando campo: {e}")

    def _select_date_of_birth(self, driver, wait):
        SPANISH_MONTHS = {
            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
            "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
            "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
        }
        
        mes_raw = self._datos.get("mes_nacimiento", "").strip().lower()
        mes_val = SPANISH_MONTHS.get(mes_raw, mes_raw)
        if len(mes_val) == 1 and mes_val.isdigit():
            mes_val = mes_val.zfill(2)
        
        dia_val = self._datos.get("dia_nacimiento", "").strip()
        if dia_val.isdigit():
            dia_val = dia_val.zfill(2)
            
        anio_val = self._datos.get("anio_nacimiento", "").strip()

        # Comprobar si el ID 'day' es un input de tipo texto (DD/MM/AAAA)
        try:
            day_el = driver.find_element(By.ID, "day")
            if day_el.get_attribute("type") == "text":
                full_date = f"{dia_val}/{mes_val}/{anio_val}"
                self._fill_text_field(driver, day_el, full_date)
                logger.info(f"✅ DOB ingresada en campo de texto único: {full_date}")
                return
        except Exception as e:
            pass

        # Si no es un campo de texto, continuar con el flujo original de 3 dropdowns
        for val, selectors in [
            (dia_val, ["//select[@id='day']", "//select[contains(@aria-label, 'Día')]", "//select[@id='dob_day']"]),
            (mes_val, ["//select[@id='month']", "//select[contains(@aria-label, 'Mes')]", "//select[@id='dob_month']"]),
            (anio_val, ["//select[@id='year']", "//select[contains(@aria-label, 'Año')]", "//select[@id='dob_year']"])
        ]:
            el = self._find_input_field(driver, wait, selectors)
            if el:
                try:
                    s = Select(el)
                    try:
                        s.select_by_value(val)
                        logger.info(f"✅ DOB seleccionado por valor: {val}")
                        continue
                    except: pass
                    
                    try:
                        s.select_by_visible_text(val)
                        logger.info(f"✅ DOB seleccionado por texto visible: {val}")
                        continue
                    except: pass
                    
                    if val.startswith("0") and len(val) == 2:
                        try:
                            s.select_by_value(val[1:])
                            logger.info(f"✅ DOB seleccionado por valor alternativo (sin cero): {val[1:]}")
                            continue
                        except: pass
                        try:
                            s.select_by_visible_text(val[1:])
                            logger.info(f"✅ DOB seleccionado por texto alternativo (sin cero): {val[1:]}")
                            continue
                        except: pass
                except Exception as e:
                    logger.warning(f"Error al seleccionar DOB dropdown: {e}")

    def _select_radio_buttons(self, driver):
        mapping = {
            "tiene_tdc": ("owncard_one", "owncard_two"),
            "tiene_auto": ("carcredit_one", "carcredit_two"),
            "tiene_hipoteca": ("homecredit_one", "homecredit_two")
        }
        for campo, (id_yes, id_no) in mapping.items():
            is_yes = self._datos.get(campo, "no").lower() == "si"
            target_id = id_yes if is_yes else id_no
            try:
                radio_el = driver.find_element(By.ID, target_id)
                driver.execute_script("arguments[0].click();", radio_el)
                logger.info(f"✅ [AMEX Async] Radio clickeado por ID: {campo} -> {target_id}")
            except Exception as e:
                logger.warning(f"Error clickeando radio {campo} ({target_id}): {e}")
