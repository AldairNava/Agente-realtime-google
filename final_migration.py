import os
import shutil
from pathlib import Path

def run_migration():
    base_dir = Path(__file__).parent.absolute()
    assets_dir = base_dir / "assets"
    tools_dir = base_dir / "tools"
    knowledge_dir = base_dir / "knowledge"

    # 1. Mover de knowledge/ a assets/*/rag_docs/
    if knowledge_dir.exists():
        # amex
        if (knowledge_dir / "amex_catalog.json").exists():
            shutil.move(str(knowledge_dir / "amex_catalog.json"), str(assets_dir / "amex" / "rag_docs" / "amex_catalog.json"))
        # retencion
        if (knowledge_dir / "retencion_knowledge.json").exists():
            shutil.move(str(knowledge_dir / "retencion_knowledge.json"), str(assets_dir / "retencion" / "rag_docs" / "retencion_knowledge.json"))
        # plata
        if (knowledge_dir / "plata_knowledge.json").exists():
            shutil.move(str(knowledge_dir / "plata_knowledge.json"), str(assets_dir / "plata" / "rag_docs" / "plata_knowledge.json"))
        # ventas_izzi
        if (knowledge_dir / "knowledge_base.json").exists():
            shutil.move(str(knowledge_dir / "knowledge_base.json"), str(assets_dir / "ventas_izzi" / "rag_docs" / "knowledge_base.json"))
        if (knowledge_dir / "mundial_2026.json").exists():
            shutil.move(str(knowledge_dir / "mundial_2026.json"), str(assets_dir / "ventas_izzi" / "rag_docs" / "mundial_2026.json"))
        
        # delete folder if empty
        try:
            os.rmdir(str(knowledge_dir))
            print("[OK] Carpeta knowledge/ eliminada.")
        except OSError:
            print("[WARN] Carpeta knowledge/ no está vacía.")

    # 2. Crear subcarpetas en tools/ y mover scripts
    campaigns = ["amex", "retencion", "plata", "ventas_izzi"]
    for c in campaigns:
        (tools_dir / c).mkdir(exist_ok=True)
        # Touch __init__.py so python recognizes them as modules
        (tools_dir / c / "__init__.py").touch()

    # Mover tools de amex
    if (tools_dir / "amex_form.py").exists():
        shutil.move(str(tools_dir / "amex_form.py"), str(tools_dir / "amex" / "amex_form.py"))

    # Mover tools de plata
    if (tools_dir / "plata_tools.py").exists():
        shutil.move(str(tools_dir / "plata_tools.py"), str(tools_dir / "plata" / "plata_tools.py"))

    # Mover tools de retencion
    for f in ["genesys_rpa.py", "retencion_rpa.py", "retencion_tools.py", "siebel_casos_negocio.py", "siebel_retencion_rpa.py"]:
        if (tools_dir / f).exists():
            shutil.move(str(tools_dir / f), str(tools_dir / "retencion" / f))

    print("[OK] Archivos tools/ movidos.")

    # 3. Limpieza de raíz
    # spec a ventas_izzi
    if (base_dir / "spec_agente_voz_ia_autoinstalacion_izzi_tv.md").exists():
        shutil.move(str(base_dir / "spec_agente_voz_ia_autoinstalacion_izzi_tv.md"), str(assets_dir / "ventas_izzi" / "spec_agente_voz_ia_autoinstalacion_izzi_tv.md"))

    # borrar basura
    for trash in ["error.log", "vicidial_agent_events.log", "phantom_after_direct_login.png", "phantom_main_screen.png", "test_conexiones.txt"]:
        fpath = base_dir / trash
        if fpath.exists():
            fpath.unlink()
    
    print("[OK] Archivos de la raíz limpiados.")

if __name__ == "__main__":
    run_migration()
