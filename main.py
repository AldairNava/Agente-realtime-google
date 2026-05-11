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

    parser.add_argument("--mode", choices=["local", "produccion"], default="local",
                        help="Entorno de ejecución: 'local' (micro) o 'produccion' (SIP/Vicidial)")

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
    # MODO BATCH: --txt 1  →  graba TODOS los .txt de la campaña
    # ---------------------------------------------------------------
    if args.voice == "grabacion" and args.txt == "1":
        textos_dir = os.path.join(os.path.dirname(__file__), 'config', f'textos_audios_{args.campania}')
        if not os.path.isdir(textos_dir):
            logger.error(f"❌ No existe la carpeta de textos: {textos_dir}")
            return

        archivos_txt = sorted([f[:-4] for f in os.listdir(textos_dir) if f.endswith('.txt')])
        if not archivos_txt:
            logger.error(f"❌ No hay archivos .txt en: {textos_dir}")
            return

        logger.info("=" * 52)
        logger.info(f"  🎙️  MODO BATCH — CAMPAÑA: {args.campania.upper()}")
        logger.info(f"  Total de audios a grabar: {len(archivos_txt)}")
        logger.info("=" * 52)

        audio_interface = LocalAudioInterface(chunk=512)
        try:
            for i, nombre in enumerate(archivos_txt, 1):
                logger.info(f"\n[{i}/{len(archivos_txt)}] ➜ Grabando: {nombre}.txt ...")
                await grabar_un_audio(api_key, audio_interface, args.campania, nombre)
                logger.info(f"✅ [{i}/{len(archivos_txt)}] {nombre}.wav guardado. Pausa 2s...")
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
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'voice_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        sip = cfg['sip_config']
        audio_interface = SipAudioInterface(
            server=os.getenv('SIP_SERVER_IP', sip.get('server_ip')),
            port=int(os.getenv('SIP_PORT', sip.get('port', 5060))),
            user=os.getenv('SIP_EXTENSION', sip.get('extension')),
            password=os.getenv('SIP_PASSWORD', sip.get('password'))
        )
    else:
        audio_interface = LocalAudioInterface(chunk=512)

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
        return
    except Exception as e:
        logger.error(f"Error inicializando el agente: {e}")
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
        await asyncio.sleep(0.5)
        logger.info("Sistemas de Hardware Liberados. Adiós.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEjecución Terminada por Terminal (Nivel OS).")
