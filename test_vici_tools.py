import logging
import json
import os
import sys

# Añadir el path actual para importar localmente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tools.dispatcher import ToolDispatcher
from tools.vicidial_api import VicidialAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestVici")

def test_integration():
    # Mock config
    config = {
        "vicidial_api": {
            "host": "localhost",
            "user": "cron",
            "password": "1234",
            "agent_user": "1001",
            "source": "test_script"
        }
    }
    
    logger.info("Iniciando ToolDispatcher...")
    dispatcher = ToolDispatcher(config)
    
    logger.info(f"Herramientas registradas: {[t.__name__ for t in dispatcher.get_tool_list()]}")
    
    # Verificar que las herramientas de Vicidial están ahí
    required_tools = ['external_hangup', 'external_status', 'external_pause', 'pause_code']
    for tool in required_tools:
        if tool in dispatcher._map:
            logger.info(f"✅ Herramienta '{tool}' registrada correctamente.")
        else:
            logger.error(f"❌ Herramienta '{tool}' NO encontrada.")

    # Prueba de ejecución (simulada - fallará si no hay servidor real, pero probamos el flujo)
    logger.info("Probando ejecución de 'external_pause' (simulado)...")
    res = dispatcher.execute_tool("external_pause", {"paused": True})
    logger.info(f"Resultado: {res}")

if __name__ == "__main__":
    test_integration()
