"""
AMEX Form Automation — Llenado automático del formulario Platinum Credit Card
=============================================================================
Usa Selenium para llenar y enviar el formulario de solicitud de AMEX con los
datos capturados durante la llamada por el agente de ventas.

Tools expuestas a Gemini:
- guardar_dato_cliente(campo, valor)
- ver_datos_capturados()
- enviar_solicitud_amex()
"""

import os
import time
import logging
import threading
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger("AMEXForm")

# URL del formulario con parámetros de tracking
AMEX_FORM_URL = (
    "https://www.americanexpress.com/es-mx/tarjetas-de-servicio/formulario"
    "/clusters/the-platinum-credit-card"
    "?sourcecode=A0000HNXUN&cpid=100591683"
    "&utm_source=lead2business&utm_medium=affiliates"
    "&utm_campaign=Lead2BusinessAsistidoGRCCPlatinumCreditCardCashback"
    "&utm_content=GRCCPlatinumCreditCard"
)

# Campos del formulario y su mapeo a nombre interno
# Campos del formulario (Versión ShortApp)
CAMPOS_REQUERIDOS = {
    "nombre": "Nombre(s) y Apellidos del cliente",
    "fecha_nacimiento": "Fecha de nacimiento (ej: 15 de Mayo de 1990)",
    "email": "Correo electrónico",
    "celular": "Número telefónico (10 dígitos)"
}


class AMEXFormHandler:
    """Maneja la captura de datos durante la llamada y el envío del formulario AMEX."""

    def __init__(self):
        self._datos = {}
        self._resultado_envio = None
        self._screenshot_path = None

    # ═══════════════════════════════════════════
    #  TOOLS EXPUESTAS A GEMINI
    # ═══════════════════════════════════════════

    def guardar_dato_cliente(self, campo: str, valor: str) -> str:
        """
        Guarda un dato capturado del cliente durante la conversación.
        Llama esta herramienta cada vez que el cliente proporcione un dato.

        Args:
            campo: Nombre del campo. Opciones válidas: nombre, apellido_paterno,
                   apellido_materno, dia_nacimiento, mes_nacimiento, anio_nacimiento,
                   rfc, email, celular, codigo_postal, tiene_tdc, tiene_auto, tiene_hipoteca
            valor: El valor proporcionado por el cliente

        Returns:
            Confirmación del dato guardado y lista de datos faltantes.
        """
        campo = campo.strip().lower()

        if campo not in CAMPOS_REQUERIDOS:
            return (
                f"Error: Campo '{campo}' no es válido. "
                f"Campos válidos: {', '.join(CAMPOS_REQUERIDOS.keys())}"
            )

        # Normalizar valores booleanos
        if campo in ("tiene_tdc", "tiene_auto", "tiene_hipoteca"):
            valor_lower = valor.strip().lower()
            if valor_lower in ("sí", "si", "yes", "s", "1", "true", "correcto", "afirmativo"):
                valor = "si"
            else:
                valor = "no"

        self._datos[campo] = valor.strip()
        logger.info(f"📝 [AMEX] Dato guardado: {campo} = '{valor.strip()}'")

        # Calcular faltantes
        faltantes = [c for c in CAMPOS_REQUERIDOS if c not in self._datos]

        if not faltantes:
            return (
                f"✅ Dato '{campo}' guardado. ¡TODOS LOS DATOS ESTÁN COMPLETOS! "
                f"Ya puedes usar la herramienta 'enviar_solicitud_amex' para enviar la solicitud."
            )

        faltantes_desc = [f"'{c}' ({CAMPOS_REQUERIDOS[c]})" for c in faltantes]
        return (
            f"✅ Dato '{campo}' guardado correctamente. "
            f"Datos capturados: {len(self._datos)}/{len(CAMPOS_REQUERIDOS)}. "
            f"Faltan: {', '.join(faltantes_desc)}"
        )

    def ver_datos_capturados(self) -> str:
        """
        Muestra todos los datos capturados y los que faltan.
        Usa esta herramienta para verificar qué información ya tienes antes de enviar.

        Returns:
            Resumen de datos capturados y faltantes.
        """
        if not self._datos:
            return (
                "No se ha capturado ningún dato aún. "
                f"Campos requeridos: {', '.join(CAMPOS_REQUERIDOS.keys())}"
            )

        capturados = []
        faltantes = []
        for campo, desc in CAMPOS_REQUERIDOS.items():
            if campo in self._datos:
                # Ocultar parcialmente datos sensibles
                val = self._datos[campo]
                if campo == "rfc":
                    val = val[:4] + "****" + val[-3:] if len(val) > 7 else val
                elif campo == "celular":
                    val = val[:3] + "****" + val[-3:] if len(val) > 6 else val
                capturados.append(f"  ✅ {campo}: {val}")
            else:
                faltantes.append(f"  ❌ {campo} ({desc})")

        resultado = f"DATOS CAPTURADOS ({len(self._datos)}/{len(CAMPOS_REQUERIDOS)}):\n"
        resultado += "\n".join(capturados)
        if faltantes:
            resultado += f"\n\nDALTOS FALTANTES ({len(faltantes)}):\n"
            resultado += "\n".join(faltantes)
        else:
            resultado += "\n\n🎉 ¡TODOS LOS DATOS COMPLETOS! Listo para enviar."

        return resultado

    def enviar_solicitud_amex(self) -> str:
        """
        Envía la solicitud de tarjeta Platinum AMEX llenando el formulario web
        con los datos capturados. Requiere que TODOS los campos estén completos.

        Returns:
            Resultado del envío: éxito o error con detalle.
        """
        # Verificar que todos los campos estén completos
        faltantes = [c for c in CAMPOS_REQUERIDOS if c not in self._datos]
        if faltantes:
            return (
                f"Error: Faltan datos obligatorios: {', '.join(faltantes)}. "
                "Captura todos los datos antes de enviar."
            )

        logger.info("🚀 [AMEX] Iniciando envío de solicitud simulado (ShortApp)...")

        try:
            # Mock successful submission
            resultado = (
                "ÉXITO: La solicitud de Tarjeta Platinum (ShortApp) fue registrada. "
                "Ahora DEBES inyectar los comentarios usando 'actualizar_comentarios_cliente' "
                "y luego transferir la llamada usando 'transfer_conference'."
            )
            self._resultado_envio = resultado
            logger.info("✅ [AMEX] Envío simulado exitoso.")
            return resultado
        except Exception as e:
            error_msg = f"Error al procesar formulario: {str(e)}"
            logger.error(f"❌ [AMEX] {error_msg}")
            self._resultado_envio = error_msg
            return error_msg

    # ═══════════════════════════════════════════
    #  SELENIUM — LLENADO DEL FORMULARIO
    # ═══════════════════════════════════════════

    def _fill_and_submit_form(self) -> str:
        """Abre Chrome, navega al formulario, llena los campos y envía."""
        tmp_user_data = tempfile.mkdtemp(prefix="amex_chrome_")
        driver = None

        try:
            chrome_options = Options()
            chrome_options.add_argument(f"--user-data-dir={tmp_user_data}")
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--ignore-certificate-errors")
            chrome_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            wait = WebDriverWait(driver, 15)

            # 1. Navegar al formulario
            logger.info(f"🌐 [AMEX] Cargando formulario...")
            driver.get(AMEX_FORM_URL)
            time.sleep(3)

            # 2. Esperar a que cargue el formulario
            # Buscar el primer campo de texto (Nombre)
            nombre_field = self._find_input_field(driver, wait, [
                "//input[contains(@aria-label, 'Nombre')]",
                "//input[contains(@placeholder, 'nombre')]",
                "//input[@id='name']",
                "//input[@name='name']",
                "(//input[@type='text'])[1]",
            ])

            if not nombre_field:
                driver.save_screenshot("amex_form_not_found.png")
                return "Error: No se encontró el formulario de AMEX. El sitio puede estar caído."

            logger.info("📋 [AMEX] Formulario cargado. Llenando campos...")

            # 3. Llenar campos de texto
            self._fill_text_field(driver, wait, nombre_field, self._datos["nombre"])

            # Apellido Paterno
            ap_field = self._find_input_field(driver, wait, [
                "//input[contains(@aria-label, 'paterno')]",
                "//input[@id='fathersurname']",
                "//input[@name='fathersurname']",
                "(//input[@type='text'])[2]",
            ])
            if ap_field:
                self._fill_text_field(driver, wait, ap_field, self._datos["apellido_paterno"])

            # Apellido Materno
            am_field = self._find_input_field(driver, wait, [
                "//input[contains(@aria-label, 'materno')]",
                "//input[@id='mothersurname']",
                "//input[@name='mothersurname']",
                "(//input[@type='text'])[3]",
            ])
            if am_field:
                self._fill_text_field(driver, wait, am_field, self._datos["apellido_materno"])

            # 4. Fecha de nacimiento (dropdowns)
            self._select_date_of_birth(driver, wait)

            # 5. RFC
            rfc_field = self._find_input_field(driver, wait, [
                "//input[contains(@aria-label, 'RFC')]",
                "//input[@id='rfc']",
                "//input[@name='rfc']",
                "//input[contains(@placeholder, 'AAAA')]",
            ])
            if rfc_field:
                self._fill_text_field(driver, wait, rfc_field, self._datos["rfc"])

            # 6. Email
            email_field = self._find_input_field(driver, wait, [
                "//input[@type='email']",
                "//input[contains(@aria-label, 'correo')]",
                "//input[@id='email']",
                "//input[contains(@placeholder, 'nombre@')]",
            ])
            if email_field:
                self._fill_text_field(driver, wait, email_field, self._datos["email"])

            # 7. Celular
            cel_field = self._find_input_field(driver, wait, [
                "//input[@type='tel']",
                "//input[contains(@aria-label, 'celular')]",
                "//input[@id='mobile']",
                "//input[contains(@aria-label, '10')]",
            ])
            if cel_field:
                self._fill_text_field(driver, wait, cel_field, self._datos["celular"])

            # 8. Código Postal
            cp_field = self._find_input_field(driver, wait, [
                "//input[contains(@aria-label, 'postal')]",
                "//input[@id='zipcode']",
                "//input[@name='zipcode']",
            ])
            if cp_field:
                self._fill_text_field(driver, wait, cp_field, self._datos["codigo_postal"])

            # 9. Radio buttons (Sí/No)
            self._select_radio_buttons(driver, wait)

            # Screenshot pre-envío
            driver.save_screenshot("amex_form_filled.png")
            logger.info("📸 [AMEX] Screenshot del formulario llenado guardado.")

            # 10. Scroll al botón Enviar y hacer clic
            enviar_btn = self._find_input_field(driver, wait, [
                "//button[contains(text(), 'Enviar')]",
                "//input[@type='submit']",
                "//button[@type='submit']",
                "//*[contains(text(), 'Enviar')]",
            ])

            if enviar_btn:
                driver.execute_script("arguments[0].scrollIntoView(true);", enviar_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", enviar_btn)
                logger.info("📤 [AMEX] Botón Enviar clickeado.")
                time.sleep(5)

                # Screenshot post-envío
                driver.save_screenshot("amex_form_submitted.png")

                # Verificar resultado
                page_text = driver.page_source.lower()
                if any(w in page_text for w in ["verificación", "sms", "código", "éxito", "enviado", "felicidades"]):
                    logger.info("✅ [AMEX] ¡Solicitud enviada con éxito!")
                    return (
                        "ÉXITO: La solicitud de Tarjeta Platinum fue enviada correctamente. "
                        "El cliente recibirá un SMS de verificación en su celular. "
                        "Informa al cliente y despídete usando 'amex_exito' y luego 'amex_despedida'."
                    )
                elif any(w in page_text for w in ["error", "inválido", "incorrecto"]):
                    logger.warning("⚠️ [AMEX] El formulario reportó errores de validación.")
                    return (
                        "ADVERTENCIA: El formulario reportó errores de validación. "
                        "Es posible que algún dato sea incorrecto. Verifica RFC y correo con el cliente."
                    )
                else:
                    return (
                        "ENVIADO: El formulario fue enviado. No se pudo confirmar el resultado exacto. "
                        "Informa al cliente que su solicitud fue procesada."
                    )
            else:
                return "Error: No se encontró el botón de enviar en el formulario."

        except Exception as e:
            logger.error(f"❌ [AMEX] Error en Selenium: {e}")
            if driver:
                driver.save_screenshot("amex_form_error.png")
            return f"Error técnico al procesar el formulario: {str(e)}"

        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            try:
                shutil.rmtree(tmp_user_data, ignore_errors=True)
            except:
                pass

    # ═══════════════════════════════════════════
    #  HELPERS DE SELENIUM
    # ═══════════════════════════════════════════

    def _find_input_field(self, driver, wait, selectors):
        """Intenta encontrar un campo del formulario con múltiples selectores."""
        for selector in selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element.is_displayed():
                    return element
            except:
                continue
        return None

    def _fill_text_field(self, driver, wait, element, value):
        """Limpia y llena un campo de texto usando JavaScript para máxima compatibilidad."""
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.3)
            element.click()
            time.sleep(0.2)
            element.clear()
            # Usar JS para disparar eventos de React/Angular
            driver.execute_script(
                """
                var el = arguments[0];
                var value = arguments[1];
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeInputValueSetter.call(el, value);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                """,
                element, value
            )
            logger.info(f"  ✏️ Campo llenado: '{value[:30]}...'")
        except Exception as e:
            logger.warning(f"  ⚠️ Error llenando campo: {e}")

    def _select_date_of_birth(self, driver, wait):
        """Selecciona día, mes y año en los dropdowns de fecha de nacimiento."""
        dia = self._datos.get("dia_nacimiento", "").strip()
        mes = self._datos.get("mes_nacimiento", "").strip()
        anio = self._datos.get("anio_nacimiento", "").strip()

        # Intentar con selectores para dropdowns
        day_selectors = [
            "//select[contains(@aria-label, 'Día') or contains(@aria-label, 'día')]",
            "//select[@id='dob_day']",
            "(//select)[1]",
        ]
        month_selectors = [
            "//select[contains(@aria-label, 'Mes') or contains(@aria-label, 'mes')]",
            "//select[@id='dob_month']",
            "(//select)[2]",
        ]
        year_selectors = [
            "//select[contains(@aria-label, 'Año') or contains(@aria-label, 'año')]",
            "//select[@id='dob_year']",
            "(//select)[3]",
        ]

        for selectors, value, label in [
            (day_selectors, dia, "Día"),
            (month_selectors, mes, "Mes"),
            (year_selectors, anio, "Año"),
        ]:
            el = self._find_input_field(driver, wait, selectors)
            if el:
                try:
                    select = Select(el)
                    # Intentar por valor directo o por texto visible
                    try:
                        select.select_by_value(value)
                    except:
                        try:
                            select.select_by_visible_text(value)
                        except:
                            # Intentar con valor con cero al inicio (01, 02...)
                            select.select_by_value(value.zfill(2))
                    logger.info(f"  📅 {label}: {value}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Error seleccionando {label}: {e}")

    def _select_radio_buttons(self, driver, wait):
        """Selecciona las opciones Sí/No en los radio buttons."""
        radio_config = [
            ("tiene_tdc", "tarjeta", "crédito"),
            ("tiene_auto", "automotriz", "auto"),
            ("tiene_hipoteca", "hipotecario", "hipoteca"),
        ]

        for campo, keyword1, keyword2 in radio_config:
            valor = self._datos.get(campo, "no").lower()
            is_yes = valor in ("si", "sí", "yes")

            # Buscar el grupo de radios por el texto de la pregunta
            try:
                # Buscar todos los radios y agrupar
                radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                # Intentar encontrar por label/text cercano
                labels = driver.find_elements(
                    By.XPATH,
                    f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                    f"'abcdefghijklmnopqrstuvwxyz'), '{keyword1}') or "
                    f"contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                    f"'abcdefghijklmnopqrstuvwxyz'), '{keyword2}')]"
                    f"/ancestor::*[.//input[@type='radio']]"
                )

                if labels:
                    container = labels[0]
                    group_radios = container.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    group_labels = container.find_elements(By.TAG_NAME, "label")

                    for radio, label in zip(group_radios, group_labels):
                        label_text = label.text.strip().lower()
                        if (is_yes and label_text in ("sí", "si")) or \
                           (not is_yes and label_text == "no"):
                            driver.execute_script("arguments[0].click();", radio)
                            logger.info(f"  🔘 {campo}: {'Sí' if is_yes else 'No'}")
                            break
            except Exception as e:
                logger.warning(f"  ⚠️ Error seleccionando radio {campo}: {e}")
