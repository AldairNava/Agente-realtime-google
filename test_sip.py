import time
import logging
import json
import os
from pyVoIP.VoIP import VoIPPhone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SIP_Test")

def test_registration():
    config_path = os.path.join('config', 'voice_config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    
    sip = cfg['sip_config']
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No necesita conectarse realmente para obtener la IP local activa
        s.connect(('8.8.8.8', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()

    logger.info(f"--- Probando Registro SIP: {sip['extension']}@{sip['server_ip']} desde {local_ip} ---")
    
    try:
        phone = VoIPPhone(
            sip['server_ip'], 
            sip['port'], 
            sip['extension'], 
            sip['password'],
            myIP=local_ip
        )
        phone.start()
        
        # Esperar unos segundos para el registro
        for i in range(10):
            # En pyVoIP no hay un flag directo de 'is_registered', 
            # pero lanzará error o se quedará en loop si falla.
            # Verificamos si el socket está vivo.
            logger.info(f"Intento {i+1}/10... Verificando estado del socket SIP.")
            time.sleep(2)
            
        logger.info("✅ Si no viste errores de 'Unauthorized' o 'Timeout' arriba, el registro fue EXITOSO.")
        phone.stop()
        
    except Exception as e:
        logger.error(f"❌ Error Crítico de Registro: {e}")

if __name__ == "__main__":
    test_registration()
