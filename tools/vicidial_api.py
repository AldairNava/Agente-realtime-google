import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class VicidialAPI:
    """Implementa la Agent API de Vicidial (agc/api.php)"""
    
    def __init__(self, config: dict):
        self.host = config.get('host') or "127.0.0.1" # Default local si falta
        self.url = f"http://{self.host}/agc/api.php"
        self.non_agent_url = f"http://{self.host}/vicidial/non_agent_api.php"
        self.user = config.get('user')
        self.password = config.get('password')
        self.agent_user = config.get('agent_user') or self.user
        self.source = config.get('source', 'gemini_agent')
        
        # Datos de logueo robusto
        self.phone_login = config.get('phone_login')
        self.phone_pass = config.get('phone_pass')
        self.campaign_id = config.get('campaign_id')
        
        # Bandera para rastrear si se llamó a external_status
        self._status_called = False
        self.call_hungup_sent = False
        self._pending_status = None
        self.last_status_sent = "SIN_ESTATUS"
        self.phantom = None

    def external_login(self):
        """
        Realiza un logueo robusto del agente en la campaña.
        Requiere phone_login, phone_pass y campaign_id en la configuración.
        """
        if not all([self.phone_login, self.phone_pass, self.campaign_id]):
            return "ERROR: Faltan credenciales de teléfono o campaña para external_login."
            
        params = {
            "phone_login": self.phone_login,
            "phone_pass": self.phone_pass,
            "campaign_id": self.campaign_id,
            "protocol": "SIP",
            "phone_code": "1",
            "outbound_autodial": "Y",
            "preview": "NO",
            "focus": "YES"
        }
        return self._call_api("external_login", params)

    def external_dial(self, phone_number: str, search: str = "YES"):
        """Realiza una llamada manual a través del API."""
        params = {
            "value": phone_number,
            "phone_code": "1",
            "search": search
        }
        return self._call_api("external_dial", params)

    def _call_api(self, function: str, extra_params: Optional[dict] = None, use_non_agent: bool = False) -> str:
        api_url = self.non_agent_url if use_non_agent else self.url
        params = {
            "source": self.source,
            "user": self.user,
            "pass": self.password,
            "agent_user": self.agent_user,
            "function": function
        }
        if extra_params:
            params.update(extra_params)

        try:
            # Construir URL para log (ocultando pass)
            safe_params = {k: (v if k != 'pass' else '****') for k, v in params.items()}
            full_url = f"{api_url}?{'&'.join([f'{k}={v}' for k, v in safe_params.items()])}"
            logger.info(f"🔗 [API URL]: {full_url}")

            response = requests.get(api_url, params=params, timeout=5)
            response.raise_for_status()
            logger.info(f"VICIDIAL API [{function}]: {response.text}")
            return response.text
        except Exception as e:
            logger.error(f"Error en VICIDIAL API [{function}]: {e}")
            return f"Error: {e}"

    def external_hangup(self):
        """Cuelga la llamada activa del agente y tipifica con la de espera (o fallback) tras 3 segundos."""
        if getattr(self, 'call_hungup_sent', False):
            logger.info("🛑 [VicidialAPI] external_hangup already called, skipping duplicate.")
            return "SUCCESS: already hung up"
        self.call_hungup_sent = True
        
        # Guardar una copia local del status antes de dormir para evitar condiciones de carrera
        status_to_send = self._pending_status if self._pending_status else "NI"
        
        # 1. Colgar la llamada inmediatamente
        logger.info("🛑 [VicidialAPI] Ejecutando colgado de canal (external_hangup)...")
        res_hangup = self._call_api("external_hangup", {"value": "1"})
        
        # 1.1 Ejecutar fallback directo en el navegador si está disponible para asegurar el colgado físico
        if getattr(self, 'phantom', None):
            try:
                self.phantom.hangup_call_browser()
            except Exception as pe:
                logger.error(f"Error en fallback de colgado en navegador: {pe}")
        
        # 2. Esperar obligatoriamente 3 segundos a que cargue la pantalla de disposición de Vicidial
        import time
        logger.info("⏳ [VicidialAPI] Esperando 3 segundos en pantalla de disposición antes de tipificar...")
        time.sleep(3.0)
        
        # 3. Aplicar la tipificación guardada (o fallback "NI")
        logger.warning(f"💾 [VicidialAPI] Enviando tipificación de cierre: {status_to_send}")
        self.last_status_sent = status_to_send
        
        # Llamar a la API real de external_status
        res_status = self._call_api("external_status", {"value": status_to_send})
        
        # Limpiar variables para la siguiente llamada
        self._pending_status = None
        self._status_called = False
        
        return f"{res_hangup} | {res_status}"

    def external_status(self, status: str):
        """Guarda la tipificación elegida por el agente de forma diferida."""
        logger.info(f"📥 [VicidialAPI] Guardando tipificación pendiente: {status} (Se enviará al colgar)")
        self._pending_status = status
        self._status_called = True
        self.last_status_sent = status
        return f"SUCCESS: Tipificación '{status}' guardada de forma diferida. Se aplicará al colgar."

    def external_pause(self, paused: bool = True):
        """Pone o quita la pausa al agente."""
        value = "PAUSE" if paused else "RESUME"
        return self._call_api("external_pause", {"value": value})

    def pause_code(self, code: str):
        """Establece un código de pausa (AUX, BREAK, MEAL, etc.)."""
        return self._call_api("pause_code", {"value": code})

    def transfer_conference(self, ingroup: str, value: str = "1") -> str:
        """
        Transfiere la llamada activa a un ingroup/grupo de entrante en Vicidial.
        """
        logger.info(f"🔄 [VicidialAPI] Ejecutando transferencia real a la cola {ingroup}...")
        try:
            res = self._call_api("transfer_conference", {
                "value": "LOCAL_CLOSER",
                "ingroup_choices": ingroup
            })
            logger.info(f"VICIDIAL API [transfer_conference] Resultado: {res}")
            return f"RESULTADO: {res}"
        except Exception as e:
            logger.error(f"Error en transferencia a {ingroup}: {e}")
            return f"ERROR: {e}"

    def generar_folio_cancelacion(self, phone: str = ""):
        """Genera un folio de cancelación único para el cliente."""
        import random
        import string
        prefix = "IZ"
        suffix = ''.join(random.choices(string.digits, k=6))
        folio = f"{prefix}-{suffix}"
        logger.info(f"Folio generado para {phone}: {folio}")
        return folio

    def get_agent_status(self) -> dict:
        """Obtiene y parsea el estado actual del agente en Vicidial."""
        # --- NUEVO: Usar Non-Agent API para el estatus ---
        raw_res = self._call_api("agent_status", use_non_agent=True)
        # Formato Non-Agent: SUCCESS: agent_status - 7900|7900|7900|PAUSED|...
        data = {"raw": raw_res, "status": "UNKNOWN", "lead_id": "0"}
        if "SUCCESS" in raw_res:
            parts = raw_res.split("|")
            if len(parts) > 3:
                data["status"] = parts[3].strip() # El estatus suele ser la 4ta posición
            if len(parts) > 5:
                # Búsqueda manual de lead_id en el pipe-delimited string
                for p in parts:
                    if "lead_id:" in p:
                         data["lead_id"] = p.split("lead_id:")[1].strip()
        return data

    def actualizar_comentarios_cliente(self, nombre_cliente: str, pantallas: str, paquete_ofrecido: str, cuenta: str = "", dudas_no_respondidas: str = "") -> str:
        """
        Actualiza el campo 'comments' (comentarios) del cliente en la llamada activa de Vicidial
        antes de realizar una transferencia, inyectando el valor en el DOM y llamando al script de ViciDial.
        """
        logger.info("📝 [VicidialAPI] Iniciando actualización de comentarios del cliente...")
        if not self.phantom:
            logger.warning("⚠️ [VicidialAPI] No se puede actualizar comentarios: self.phantom no está inicializado (modo local / sin browser activo).")
            return "SUCCESS (MOCKED): modo local / phantom inactivo"

        try:
            # Formatear el comentario final
            comments_formatted = f"Nombre: {nombre_cliente} | Pantallas: {pantallas} | Paquete: {paquete_ofrecido}"
            if cuenta:
                comments_formatted += f" | Cuenta: {cuenta}"
            if dudas_no_respondidas:
                comments_formatted += f" | Dudas: {dudas_no_respondidas}"

            # Código JavaScript para rellenar el textarea de comentarios y ejecutar el envío nativo
            js_code = """
            var comments_text = arguments[0];
            var commentsEl = document.getElementById('comments');
            if (commentsEl) {
                commentsEl.value = comments_text;
                if (typeof CustomerData_update === 'function') {
                    CustomerData_update('YES');
                    return 'SUCCESS: CustomerData_update executed';
                }
                if (typeof window.CustomerData_update === 'function') {
                    window.CustomerData_update('YES');
                    return 'SUCCESS: window.CustomerData_update executed';
                }
                return 'ERROR: comments textarea found but CustomerData_update function not found';
            } else {
                var iframes = document.getElementsByTagName('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    try {
                        var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                        var win = iframes[i].contentWindow;
                        var ifEl = doc.getElementById('comments');
                        if (ifEl) {
                            ifEl.value = comments_text;
                            if (typeof win.CustomerData_update === 'function') {
                                win.CustomerData_update('YES');
                                return 'SUCCESS: CustomerData_update executed in iframe';
                            }
                        }
                    } catch(e) {}
                }
                return 'ERROR: comments textarea element not found';
            }
            """
            
            logger.info("🖥️ [VicidialAPI] Inyectando comentarios en el DOM de Chrome y ejecutando CustomerData_update('YES')...")
            js_res = self.phantom.driver.execute_script(js_code, comments_formatted)
            logger.info(f"VICIDIAL JS [CustomerData_update]: {js_res}")
            
            if "SUCCESS" in js_res:
                return f"SUCCESS: {js_res} | Comentarios: {comments_formatted}"
            else:
                return f"WARNING: Petición inyectada pero se reportó: {js_res}"
        except Exception as e:
            logger.error(f"Error actualizando comentarios del cliente en navegador: {e}")
            return f"ERROR: {e}"

