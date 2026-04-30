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
        """Cuelga la llamada activa del agente."""
        return self._call_api("external_hangup", {"value": "1"})

    def external_status(self, status: str):
        """Tipifica la llamada con un código (SALE, NI, DNC, etc.)."""
        return self._call_api("external_status", {"value": status})

    def external_pause(self, paused: bool = True):
        """Pone o quita la pausa al agente."""
        value = "PAUSE" if paused else "RESUME"
        return self._call_api("external_pause", {"value": value})

    def pause_code(self, code: str):
        """Establece un código de pausa (AUX, BREAK, MEAL, etc.)."""
        return self._call_api("pause_code", {"value": code})

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
