import os
import json
import shutil
from pathlib import Path

def setup_retencion_2():
    base_dir = Path(__file__).parent.absolute()
    
    # 1. Update voice_config.json
    config_path = base_dir / "config" / "voice_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    if "retencion_2" not in config["campaigns"]:
        ret2 = json.loads(json.dumps(config["campaigns"]["retencion"]))
        ret2["name"] = "Retención Izzi 2 (Vicidial)"
        ret2["scripts_file"] = "assets/retencion_2/scripts.json"
        ret2["knowledge_file"] = "assets/retencion_2/rag_docs/retencion_knowledge.json"
        ret2["recording_dir"] = "assets/retencion_2/llamadas_grabadas"
        # Add vicidial config to enable Vicidial tools
        ret2["vicidial_api"] = {
            "campaign_id": "3002",
            "phone_login": "7900",
            "phone_pass": "Cyber123",
            "user": "dep1",
            "password": "Cyber123"
        }
        
        # Replace the tool colgar_llamada_genesis with external_hangup inside instructions
        # Since it's a huge dict, we'll convert to string, replace, convert back
        ret2_str = json.dumps(ret2)
        ret2_str = ret2_str.replace("colgar_llamada_genesis", "external_hangup")
        ret2 = json.loads(ret2_str)
        
        config["campaigns"]["retencion_2"] = ret2
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print("[OK] voice_config.json actualizado con retencion_2")

    # 2. Setup assets/retencion_2/
    a_src = base_dir / "assets" / "retencion"
    a_dest = base_dir / "assets" / "retencion_2"
    a_dest.mkdir(exist_ok=True)
    (a_dest / "llamadas_grabadas").mkdir(exist_ok=True)
    (a_dest / "rpa_signals").mkdir(exist_ok=True)
    (a_dest / "rag_docs").mkdir(exist_ok=True)
    (a_dest / "registro_de_llamadas").mkdir(exist_ok=True)
    
    if (a_src / "scripts.json").exists():
        # Replace colgar_llamada_genesis inside scripts as well
        with open(a_src / "scripts.json", "r", encoding="utf-8") as f:
            scripts_txt = f.read()
        scripts_txt = scripts_txt.replace("colgar_llamada_genesis", "external_hangup")
        with open(a_dest / "scripts.json", "w", encoding="utf-8") as f:
            f.write(scripts_txt)

    if (a_src / "rag_docs" / "retencion_knowledge.json").exists():
        shutil.copy2(str(a_src / "rag_docs" / "retencion_knowledge.json"), str(a_dest / "rag_docs" / "retencion_knowledge.json"))
    print("[OK] assets/retencion_2/ creado")

    # 3. Setup tools/retencion_2/
    t_src = base_dir / "tools" / "retencion"
    t_dest = base_dir / "tools" / "retencion_2"
    t_dest.mkdir(exist_ok=True)
    (t_dest / "__init__.py").touch()
    
    for pyfile in ["retencion_tools.py", "siebel_casos_negocio.py", "siebel_retencion_rpa.py"]:
        if (t_src / pyfile).exists():
            with open(t_src / pyfile, "r", encoding="utf-8") as f:
                code = f.read()
            # Replace paths to point to retencion_2
            code = code.replace("assets/retencion/", "assets/retencion_2/")
            code = code.replace("assets\\\\retencion\\\\", "assets\\\\retencion_2\\\\")
            # In siebel_retencion_rpa.py we might have imports like `from tools.retencion.siebel_casos_negocio`
            code = code.replace("from tools.retencion.", "from tools.retencion_2.")
            
            with open(t_dest / pyfile, "w", encoding="utf-8") as f:
                f.write(code)
    print("[OK] tools/retencion_2/ creado")

if __name__ == "__main__":
    setup_retencion_2()
