import logging
from .knowledge_rag import KnowledgeRAG
from .vicidial_db import VicidialDatabase
from .vicidial_api import VicidialAPI

logger = logging.getLogger(__name__)

class ToolDispatcher:
    """Orquestador de Tareas Inteligentes. Resuelve lo que Gemini decida ejecutar y lo devuelve."""
    def __init__(self, config: dict = None, extra_tools: list = None):
        self.rag = KnowledgeRAG()
        self.vicidial = VicidialDatabase()
        vici_cfg = (config.get('vicidial_api') if config else None) or {}
        self.api = VicidialAPI(vici_cfg)
        
        self.available_tools = [
            self.rag.consultar_datos_mundial_2026,
            self.vicidial.consultar_cliente_por_telefono,
        ]

        if self.api:
            self.available_tools.extend([
                self.api.external_hangup,
                self.api.external_status,
                self.api.external_pause,
                self.api.pause_code,
                self.api.generar_folio_cancelacion,
                self.api.external_login,
                self.api.external_dial,
                self.api.transfer_conference,
                self.api.actualizar_comentarios_cliente
            ])
            
        if extra_tools:
            self.available_tools.extend(extra_tools)
        # Mapa Inverso para ubicación algorítmica veloz
        self._map = {func.__name__: func for func in self.available_tools}

    def get_tool_list(self):
        return self.available_tools

    def execute_tool(self, tool_name: str, args: dict) -> dict:
        """Punto de Inyección llamado por el Orquestador cuando Gemini frena el audio."""
        if tool_name not in self._map:
            logger.warning(f"[Dispatcher] Gemini alucinó y pidió un tool irreal: {tool_name}")
            return {"error": f"Error 404: Herramienta '{tool_name}' inexistente en la Base del Call Center."}
            
        func = self._map[tool_name]
        try:
            resultado_final = func(**args)
            return {"resultado_oficial": resultado_final}
        except TypeError as te:
            logger.error(f"[Dispatcher] Errores en estructura de JSON de Gemini: {te}")
            return {"error": f"Error de sintaxis llamando a BBDD: {te}"}
        except Exception as e:
            logger.error(f"[Dispatcher] Caída interna: {e}")
            return {"error": f"Fallo interno del servidor: {e}"}
