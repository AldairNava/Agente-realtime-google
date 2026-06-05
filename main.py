import asyncio
import os
import logging
import argparse
from dotenv import load_dotenv
from src.agent_core import VoiceAgent
from src.audio_interfaces.local_audio import LocalAudioInterface
from src.audio_interfaces.sip_audio import SipAudioInterface

# Configuración de Observabilidad QA: Logs por Archivo y Pantalla
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler("vicidial_agent_events.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Handler especial para registrar únicamente errores en un archivo separado (error.log)
error_handler = logging.FileHandler("error.log", encoding='utf-8')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s'))
logging.getLogger().addHandler(error_handler)
logger = logging.getLogger("SystemCore")

load_dotenv()


async def grabar_un_audio(api_key, audio_interface, campania, txt_nombre):
    """Crea un agente en modo grabación, lee el .txt y genera el .wav."""
    agent = VoiceAgent(
        api_key=api_key,
        audio_interface=audio_interface,
        campania=campania,
        voice_mode='grabacion',
        execution_mode='local',
        grabacion_txt=txt_nombre,
    )
    agent_task = asyncio.create_task(agent.start())
    try:
        await agent_task
    except Exception as e:
        logger.error(f"Error grabando '{txt_nombre}': {e}")
    finally:
        agent_task.cancel()
        await asyncio.sleep(0.3)


async def main():
    parser = argparse.ArgumentParser(description="Don Pelayo - Agente de Voz Camaleónico Multi-Campaña")

    # Argumentos Principales
    parser.add_argument("--campania", type=str, required=True,
                        help="Nombre de la campaña (ej: amex, retencion, plata)")

    parser.add_argument("--mode", choices=["local", "produccion", "pruebas"], default="local",
                        help="Entorno: 'local' (micro), 'produccion' (pyVoIP+Vicidial), 'pruebas' (Zoiper+Vicidial, sin SIP interno)")
    parser.add_argument("--server", choices=["1", "2"], default="2",
                        help="Servidor Vicidial: '1' (192.168.50.121), '2' (192.168.50.66)")

    parser.add_argument("--voice", choices=["live", "hibrido", "grabacion"], default="hibrido",
                        help="Modalidad de voz: 'live' (solo IA), 'hibrido' (IA + Pregrabados) o 'grabacion'")

    # Argumentos para Modo Grabación
    parser.add_argument("--txt", type=str,
                        help="[Solo --voice grabacion] Nombre del .txt (sin extensión) en "
                             "config/textos_audios_<campania>/. "
                             "Usa '1' para grabar TODOS los .txt de la carpeta en modo batch.")
    parser.add_argument("--frase", type=str,
                        help="[Solo --voice grabacion] Frase escrita directamente en la terminal.")
    parser.add_argument("--salida", type=str,
                        help="[Solo --voice grabacion] Nombre del archivo WAV de salida (solo con --frase).")

    args = parser.parse_args()

    # Validación Modo Grabación
    if args.voice == "grabacion":
        if not args.txt and not args.frase:
            print('[ERROR] El modo grabación requiere --txt <nombre_o_1> o --frase "texto".')
            return

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("No se encontró GEMINI_API_KEY en las variables de entorno (.env)")
        return

    # ---------------------------------------------------------------
    # MODO BATCH: --txt 1  →  graba TODOS los audios del JSON
    # ---------------------------------------------------------------
    if args.voice == "grabacion" and args.txt == "1":
        import json
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'voice_config.json')
        if not os.path.exists(config_path):
            logger.error(f"❌ No existe el archivo de configuración: {config_path}")
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        campania_cfg = cfg.get('campaigns', {}).get(args.campania)
        if not campania_cfg:
            logger.error(f"❌ La campaña '{args.campania}' no está configurada en voice_config.json")
            return

        scripts_file = campania_cfg.get('scripts_file')
        if not scripts_file:
            logger.error(f"❌ No se configuró 'scripts_file' para la campaña {args.campania}")
            return

        scripts_path = os.path.join(os.path.dirname(__file__), scripts_file)
        if not os.path.exists(scripts_path):
            logger.error(f"❌ No existe el archivo de scripts: {scripts_path}")
            return

        with open(scripts_path, 'r', encoding='utf-8') as sf:
            scripts_data = json.load(sf)

        campaign_scripts = scripts_data.get('scripts', {})
        # Listar y ordenar todos los script_ids que tengan prerecord = True
        scripts_to_record = sorted([
            sid for sid, data in campaign_scripts.items() if data.get('prerecord', False)
        ])

        if not scripts_to_record:
            logger.error(f"❌ No hay scripts con 'prerecord': true en: {scripts_path}")
            return

        logger.info("=" * 52)
        logger.info(f"  🎙️  MODO BATCH — CAMPAÑA: {args.campania.upper()}")
        logger.info(f"  Total de audios a grabar: {len(scripts_to_record)}")
        logger.info("=" * 52)

        audio_interface = LocalAudioInterface(chunk=512)
        try:
            for i, nombre in enumerate(scripts_to_record, 1):
                logger.info(f"\n[{i}/{len(scripts_to_record)}] ➜ Grabando: {nombre} ...")
                await grabar_un_audio(api_key, audio_interface, args.campania, nombre)
                logger.info(f"✅ [{i}/{len(scripts_to_record)}] {nombre}.wav guardado. Pausa 2s...")
                await asyncio.sleep(2)
        finally:
            audio_interface.close()

        logger.info("\n🎉 BATCH COMPLETO. Todos los audios fueron generados.")
        return

    # ---------------------------------------------------------------
    # MODO NORMAL: un solo audio o agente en conversación completa
    # ---------------------------------------------------------------
    logger.info("=============================================")
    logger.info(f" 🚀 INICIANDO AGENTE MUNDIALISTA ")
    logger.info(f" CAMPAÑA: {args.campania.upper()} ")
    logger.info(f" ENTORNO: {args.mode.upper()} ")
    logger.info(f" VOZ    : {args.voice.upper()} ")
    logger.info("=============================================")

    audio_interface = None
    if args.mode == "produccion":
        import json
        import socket
        import pymysql
        from pymysql.cursors import DictCursor

        config_path = os.path.join(os.path.dirname(__file__), 'config', 'voice_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        server_map = {
            "1": "192.168.50.121",
            "2": "192.168.50.66"
        }
        active_host = server_map.get(args.server, "192.168.50.66")

        # Actualizar host de DB general
        import tools.vicidial_db as vdb
        vdb.DB_CONFIG["host"] = active_host

        # --- Carga dinámica de credenciales por IP del equipo ---
        ip_local = socket.gethostbyname(socket.gethostname())
        agent_user = None
        agent_alias = None
        try:
            conn = pymysql.connect(
                host=active_host,
                user='lhernandez',
                password='lhernandez10',
                database='asterisk',
                cursorclass=DictCursor,
                connect_timeout=5,
                charset='utf8mb4'
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre, alias FROM agentesDepuracion WHERE ip = %s LIMIT 1",
                    (ip_local,)
                )
                row = cur.fetchone()
            conn.close()
            if row:
                agent_user = row['nombre']
                agent_alias = row['alias']
                logger.info(f"Credenciales dinamicas: usuario={agent_user}, extension={agent_alias} (IP: {ip_local})")
            else:
                logger.warning(f"No se encontro registro en agentesDepuracion para IP {ip_local}. Usando voz_config defaults")
        except Exception as e:
            logger.error(f"Error leyendo BD de agentes: {e}")

        # --- Audio: pyVoIP como softphone automático (sin Zoiper) ---
        # pyVoIP se registra como la extensión del agente y auto-contesta las llamadas de Vicidial
        sip_extension = agent_alias or os.getenv('SIP_EXTENSION', '7929')
        sip_password = 'Cyber123'
        audio_interface = SipAudioInterface(
            server=os.getenv('SIP_SERVER_IP', active_host),
            port=int(os.getenv('SIP_PORT', 5060)),
            user=sip_extension,
            password=sip_password
        )
        logger.info(f"Audio en modo PRODUCCION: SipAudioInterface como {sip_extension}@{active_host}")

        # Inyectar credenciales dinámicas en el config de la campaña (en memoria, sin archivos tmp)
        if agent_user and agent_alias:
            sip_password = 'Cyber123'
            campania_cfg = cfg['campaigns'].get(args.campania, {})
            if 'vicidial_api' in campania_cfg:
                cfg['campaigns'][args.campania]['vicidial_api']['user'] = agent_user
                cfg['campaigns'][args.campania]['vicidial_api']['phone_login'] = agent_alias
                cfg['campaigns'][args.campania]['vicidial_api']['phone_pass'] = sip_password
                cfg['campaigns'][args.campania]['vicidial_api']['password'] = sip_password

        if 'vicidial_api' in cfg:
            cfg['vicidial_api']['host'] = active_host

        import json as _json
        os.environ['VOICE_CONFIG_INLINE'] = _json.dumps(cfg, ensure_ascii=False)
        logger.info("Config de campana actualizado con credenciales y host")


    elif args.mode == "pruebas":
        # Modo PRUEBAS: igual que produccion pero SIN pyVoIP.
        # Zoiper (instalado en el equipo) maneja el SIP y el audio va por Voicemeeter.
        # Util mientras se estabiliza la integracion pyVoIP.
        import json
        import socket
        import pymysql
        from pymysql.cursors import DictCursor

        config_path = os.path.join(os.path.dirname(__file__), 'config', 'voice_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        server_map = {
            "1": "192.168.50.121",
            "2": "192.168.50.66"
        }
        active_host = server_map.get(args.server, "192.168.50.66")

        # Actualizar host de DB general
        import tools.vicidial_db as vdb
        vdb.DB_CONFIG["host"] = active_host

        # Carga dinamica de credenciales por IP (igual que produccion)
        ip_local = socket.gethostbyname(socket.gethostname())
        agent_user = None
        agent_alias = None
        try:
            conn = pymysql.connect(
                host=active_host,
                user='lhernandez',
                password='lhernandez10',
                database='asterisk',
                cursorclass=DictCursor,
                connect_timeout=5,
                charset='utf8mb4'
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre, alias FROM agentesDepuracion WHERE ip = %s LIMIT 1",
                    (ip_local,)
                )
                row = cur.fetchone()
            conn.close()
            if row:
                agent_user = row['nombre']
                agent_alias = row['alias']
                logger.info(f"[PRUEBAS] Credenciales: usuario={agent_user}, extension={agent_alias} (IP: {ip_local})")
            else:
                logger.warning(f"[PRUEBAS] No hay registro para IP {ip_local}. Usando defaults.")
        except Exception as e:
            logger.error(f"[PRUEBAS] Error leyendo BD: {e}")

        # Audio via Voicemeeter (Zoiper maneja el SIP)
        audio_interface = LocalAudioInterface(chunk=512)
        logger.info(f"[PRUEBAS] Audio via LocalAudio/Voicemeeter (mic={os.getenv('MICROPHONE_INDEX')}, spk={os.getenv('SPEAKER_INDEX')})")
        logger.info("[PRUEBAS] Zoiper maneja el SIP — asegurate de que este registrado y con auto-respuesta ON.")

        # Inyectar credenciales dinamicas en config de campana
        if agent_user and agent_alias:
            sip_password = 'Cyber123'
            campania_cfg = cfg['campaigns'].get(args.campania, {})
            if 'vicidial_api' in campania_cfg:
                cfg['campaigns'][args.campania]['vicidial_api']['user'] = agent_user
                cfg['campaigns'][args.campania]['vicidial_api']['phone_login'] = agent_alias
                cfg['campaigns'][args.campania]['vicidial_api']['phone_pass'] = sip_password
                cfg['campaigns'][args.campania]['vicidial_api']['password'] = sip_password

        if 'vicidial_api' in cfg:
            cfg['vicidial_api']['host'] = active_host

        import json as _json
        os.environ['VOICE_CONFIG_INLINE'] = _json.dumps(cfg, ensure_ascii=False)
        logger.info("[PRUEBAS] Config actualizado con credenciales y host")

    else:
        audio_interface = LocalAudioInterface(chunk=512)

    rpa_processes = []

    def cleanup_rpas():
        if rpa_processes:
            logger.info("🛑 [Local] Cerrando procesos RPA...")
            for proc in rpa_processes:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            rpa_processes.clear()
            logger.info("✅ [Local] Procesos RPA cerrados.")

    import atexit
    atexit.register(cleanup_rpas)

    import signal
    import sys
    def handle_signal(signum, frame):
        logger.warning(f"⚠️ Proceso principal recibió señal {signum}. Limpiando y saliendo...")
        cleanup_rpas()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, handle_signal)

    if args.mode == "local" and args.campania == "retencion":
        import subprocess
        logger.info("🚀 [Local] Iniciando procesos RPA de Retención...")
        try:
            log_ret = open("retencion_rpa_console.log", "w", encoding="utf-8")
            rpa_ret = subprocess.Popen(
                [sys.executable, "tools/retencion_rpa.py", "--test"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=log_ret,
                stderr=subprocess.STDOUT
            )
            rpa_processes.append(rpa_ret)
            logger.info("✅ [Local] RPA Retención (izzi.local) iniciado (Log: retencion_rpa_console.log).")
            
            log_siebel = open("siebel_retencion_rpa_console.log", "w", encoding="utf-8")
            rpa_siebel = subprocess.Popen(
                [sys.executable, "tools/siebel_retencion_rpa.py", "--test"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=log_siebel,
                stderr=subprocess.STDOUT
            )
            rpa_processes.append(rpa_siebel)
            logger.info("✅ [Local] RPA Siebel Retención iniciado (Log: siebel_retencion_rpa_console.log).")
        except Exception as e:
            logger.error(f"❌ [Local] Error al iniciar sub-procesos RPA: {e}")

    try:
        agent = VoiceAgent(
            api_key=api_key,
            audio_interface=audio_interface,
            campania=args.campania,
            voice_mode=args.voice,
            execution_mode=args.mode,
            grabacion_txt=args.txt,
            grabacion_frase=args.frase,
            grabacion_salida=args.salida
        )
    except ValueError as ve:
        logger.error(f"Error de configuración: {ve}")
        cleanup_rpas()
        return
    except Exception as e:
        logger.error(f"Error inicializando el agente: {e}")
        cleanup_rpas()
        return

    agent_task = asyncio.create_task(agent.start())

    try:
        await agent_task
    except KeyboardInterrupt:
        logger.warning("Interrupción por Hardware (Cierre de Consola)...")
    except Exception as e:
        logger.error("Dumping Parcial de Memoria por Error Crítico: %s", str(e))
    finally:
        logger.info("Aplicando Cierre Limpio (Graceful Shutdown)... Liberando Puertos...")
        if audio_interface:
            audio_interface.close()
        agent_task.cancel()
        
        cleanup_rpas()
            
        await asyncio.sleep(0.5)
        logger.info("Sistemas de Hardware Liberados. Adiós.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEjecución Terminada por Terminal (Nivel OS).")
