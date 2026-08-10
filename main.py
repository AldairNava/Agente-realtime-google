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


def obtener_credenciales_agente(args):
    """
    Determina el usuario del agente, su alias (extensión SIP) y el host activo (servidor)
    basado en los argumentos de la terminal (usuario y/o servidor) sin consultar base de datos.
    """
    server_num = "1"
    user = args.user
    
    if user:
        user_lower = user.lower().replace(" ", "")
        if "plata" in user_lower or "virt" in user_lower or "vit" in user_lower or "amex" in user_lower:
            server_num = "2"
        elif "dep" in user_lower:
            server_num = "1"
        elif user_lower in ["3050", "3051", "3052", "3053", "3054", "3055", "7001", "7002"]:
            server_num = "2"
        elif user_lower.isdigit() and (7900 <= int(user_lower) <= 7929 or int(user_lower) == 7931):
            server_num = "1"

    # Servidor activo
    active_host = "192.168.50.66" if server_num == "2" else "192.168.50.121"

    if not user:
        if server_num == "2":
            user = "Virt1"
        else:
            user = "dep1"

    user_lower = user.lower().replace(" ", "")
    agent_user = user_lower
    agent_alias = None

    # Mapeos de Server 2
    plata_map = {
        "plata3": "3050", "plata4": "3051", "plata5": "3052",
        "plata6": "3053", "plata7": "3054", "plata8": "3055",
        "3050": "3050", "3051": "3051", "3052": "3052",
        "3053": "3053", "3054": "3054", "3055": "3055"
    }
    virt_map = {
        "virt1": "7001", "virt2": "7002",
        "vit1": "7001", "vit2": "7002",
        "7001": "7001", "7002": "7002"
    }
    amex_map = {
        "amex1": "4001", "amex2": "4002", "amex3": "4003",
        "4001": "4001", "4002": "4002", "4003": "4003"
    }

    if user_lower in plata_map:
        agent_alias = plata_map[user_lower]
        if user_lower.isdigit():
            idx = int(user_lower) - 3050 + 3
            agent_user = f"Plata{idx}"
        else:
            agent_user = user_lower.capitalize()
    elif user_lower in virt_map:
        agent_alias = virt_map[user_lower]
        if user_lower.isdigit():
            idx = int(user_lower) - 7000
            agent_user = f"Virt{idx}"
        else:
            agent_user = user_lower.capitalize().replace("Vit", "Virt")
    elif user_lower in amex_map:
        agent_alias = amex_map[user_lower]
        if user_lower.isdigit():
            idx = int(user_lower) - 4000
            agent_user = f"Amex{idx}"
        else:
            agent_user = user_lower.capitalize()
    # Mapeos de Server 1 (depX)
    elif "dep" in user_lower:
        agent_user = user_lower.lower()
        try:
            num_str = "".join([c for c in user_lower if c.isdigit()])
            if num_str:
                num = int(num_str)
                if 1 <= num <= 30:
                    agent_alias = str(7900 + num - 1)
                elif num == 31:
                    agent_alias = "7931"
            if not agent_alias:
                agent_alias = "7900"
        except Exception:
            agent_alias = "7900"
    elif user_lower.isdigit():
        val = int(user_lower)
        if 7900 <= val <= 7929:
            agent_alias = user_lower
            agent_user = f"dep{val - 7900 + 1}"
        elif val == 7931:
            agent_alias = "7931"
            agent_user = "dep31"

    # Fallbacks finales
    if not agent_alias:
        if server_num == "2":
            agent_user = "Virt1"
            agent_alias = "7001"
        else:
            agent_user = "dep1"
            agent_alias = "7900"

    logger.info(f"[MemoryResolver] Resolved user={agent_user}, extension={agent_alias}, host={active_host}")
    return agent_user, agent_alias, active_host


async def main():
    parser = argparse.ArgumentParser(description="Don Pelayo - Agente de Voz Camaleónico Multi-Campaña")

    # Argumentos Principales
    parser.add_argument("--campania", type=str, required=True,
                        help="Nombre de la campaña (ej: amex, retencion, plata)")
    parser.add_argument("--user", type=str,
                        help="Usuario o agente con el que se logueará (ej: Plata3, Plata4, Virt1)")
    parser.add_argument("--vici-campania", type=str,
                        help="ID de la campaña en Vicidial (ej: pcardVir, TVVirt) si es distinta a la del agente")
    parser.add_argument("--level", choices=["0", "1", "2", "3", "4"], default="0",
                        help="Nivel de la campaña retencion (0-4)")

    parser.add_argument("--mode", choices=["local", "produccion", "pruebas"], default="local",
                        help="Entorno: 'local' (micro), 'produccion' (pyVoIP+Vicidial), 'pruebas' (Zoiper+Vicidial, sin SIP interno)")
    # --server removido: el servidor se infiere dinámicamente según el --user proporcionado.

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

    rpa_processes = []

    # Validación Modo Producción para campañas con Vicidial
    if args.mode == "produccion" and args.campania != "retencion" and not args.user:
        print('[ERROR] El modo producción requiere el argumento --user (ej: --user Plata3) para iniciar sesión en Vicidial.')
        return

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

    # Iniciar ruido de fondo de ffplay (volumen 3%, loop infinito)
    try:
        from ruido import iniciar_ruido_background
        ruido_proc = iniciar_ruido_background()
        rpa_processes.append(ruido_proc)
        logger.info("✅ [Ruido de Fondo] ffplay iniciado en segundo plano (Volumen: 3%).")
    except Exception as e:
        logger.warning(f"⚠️ [Ruido de Fondo] No se pudo iniciar el ruido de fondo: {e}")

    audio_interface = None
    if args.mode == "produccion":
        import json
        import socket
        import pymysql
        from pymysql.cursors import DictCursor

        config_path = os.path.join(os.path.dirname(__file__), 'config', 'voice_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        # --- Carga dinámica de credenciales y host en memoria ---
        agent_user, agent_alias, active_host = obtener_credenciales_agente(args)

        # Actualizar host de DB general (Mock)
        import tools.vicidial_db as vdb
        vdb.DB_CONFIG["host"] = active_host

        # --- Audio: pyVoIP como softphone automático (sin Zoiper) ---
        # pyVoIP se registra como la extensión del agente and auto-contesta las llamadas de Vicidial
        sip_extension = agent_alias or os.getenv('SIP_EXTENSION', '7929')
        sip_password = 'Cyber123'
        
        # COMENTADO TEMPORALMENTE A PETICIÓN: NO usar SIP interno
        # audio_interface = SipAudioInterface(
        #     server=os.getenv('SIP_SERVER_IP', active_host),
        #     port=int(os.getenv('SIP_PORT', 5060)),
        #     user=sip_extension,
        #     password=sip_password
        # )
        # logger.info(f"Audio en modo PRODUCCION: SipAudioInterface como {sip_extension}@{active_host}")
        
        # En su lugar, usamos audio local/virtual
        audio_interface = LocalAudioInterface(chunk=512)
        logger.info(f"[PRODUCCION MODIFICADO] Audio vía LocalAudio/Voicemeeter (SIP Interno comentado)")

        # Inyectar credenciales dinámicas en el config de la campaña (en memoria, sin archivos tmp)
        if agent_user and agent_alias:
            sip_password = 'Cyber123'
            campania_cfg = cfg['campaigns'].get(args.campania, {})
            if 'vicidial_api' in campania_cfg:
                cfg['campaigns'][args.campania]['vicidial_api']['user'] = agent_user
                cfg['campaigns'][args.campania]['vicidial_api']['phone_login'] = agent_alias
                cfg['campaigns'][args.campania]['vicidial_api']['phone_pass'] = sip_password
                cfg['campaigns'][args.campania]['vicidial_api']['password'] = sip_password
                if 'transfer' in cfg['campaigns'][args.campania]['vicidial_api']:
                    cfg['campaigns'][args.campania]['vicidial_api']['transfer']['user'] = agent_user
                
                # Ajuste dinámico de campaign_id según el servidor asignado
                if args.campania == 'plata':
                    if active_host == "192.168.50.121":
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "3006"
                    else:
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "pcardVir"
                elif args.campania == 'amex':
                    if active_host == "192.168.50.121":
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "3006"
                    else:
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "AmexVirt"

        if args.vici_campania:
            campania_cfg = cfg['campaigns'].get(args.campania, {})
            if 'vicidial_api' in campania_cfg:
                cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = args.vici_campania

        if 'vicidial_api' in cfg:
            cfg['vicidial_api']['host'] = active_host

        # Mantener únicamente la campaña activa para evitar exceder el límite de variables de entorno en Windows
        if 'campaigns' in cfg:
            cfg['campaigns'] = {args.campania: cfg['campaigns'][args.campania]}

        import json as _json
        serialized_cfg = _json.dumps(cfg, ensure_ascii=False)
        if len(serialized_cfg) > 30000:
            override_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config', 'voice_config_override.json'))
            with open(override_path, 'w', encoding='utf-8') as f:
                f.write(serialized_cfg)
            os.environ['VOICE_CONFIG_OVERRIDE'] = override_path
            os.environ.pop('VOICE_CONFIG_INLINE', None)
        else:
            os.environ['VOICE_CONFIG_INLINE'] = serialized_cfg
            os.environ.pop('VOICE_CONFIG_OVERRIDE', None)
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

        # --- Carga dinamica de credenciales y host en memoria (igual que produccion) ---
        agent_user, agent_alias, active_host = obtener_credenciales_agente(args)

        # Actualizar host de DB general (Mock)
        import tools.vicidial_db as vdb
        vdb.DB_CONFIG["host"] = active_host

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
                if 'transfer' in cfg['campaigns'][args.campania]['vicidial_api']:
                    cfg['campaigns'][args.campania]['vicidial_api']['transfer']['user'] = agent_user
                
                # Ajuste dinámico de campaign_id según el servidor asignado
                if args.campania == 'plata':
                    if active_host == "192.168.50.121":
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "3006"
                    else:
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "pcardVir"
                elif args.campania == 'amex':
                    if active_host == "192.168.50.121":
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "3006"
                    else:
                        cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = "AmexVirt"

        if args.vici_campania:
            campania_cfg = cfg['campaigns'].get(args.campania, {})
            if 'vicidial_api' in campania_cfg:
                cfg['campaigns'][args.campania]['vicidial_api']['campaign_id'] = args.vici_campania

        if 'vicidial_api' in cfg:
            cfg['vicidial_api']['host'] = active_host

        # Mantener únicamente la campaña activa para evitar exceder el límite de variables de entorno en Windows
        if 'campaigns' in cfg:
            cfg['campaigns'] = {args.campania: cfg['campaigns'][args.campania]}

        import json as _json
        serialized_cfg = _json.dumps(cfg, ensure_ascii=False)
        if len(serialized_cfg) > 30000:
            override_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config', 'voice_config_override.json'))
            with open(override_path, 'w', encoding='utf-8') as f:
                f.write(serialized_cfg)
            os.environ['VOICE_CONFIG_OVERRIDE'] = override_path
            os.environ.pop('VOICE_CONFIG_INLINE', None)
        else:
            os.environ['VOICE_CONFIG_INLINE'] = serialized_cfg
            os.environ.pop('VOICE_CONFIG_OVERRIDE', None)
        logger.info("[PRUEBAS] Config actualizado con credenciales y host")

    else:
        audio_interface = LocalAudioInterface(chunk=512)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    def cleanup_rpas():
        override_path = os.path.join(script_dir, 'config', 'voice_config_override.json')
        if os.path.exists(override_path):
            try:
                os.remove(override_path)
            except Exception:
                pass
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

    if args.campania == "retencion":
        import subprocess
        logger.info(f"🚀 [{args.mode.capitalize()}] Iniciando procesos RPA de Retención (Genesys y Siebel)...")
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
            level=args.level,
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
