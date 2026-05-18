import os
import json

amex_json_path = r"C:\vicidial-voice-agent_multicampaña\config\amex_scripts.json"
output_dir = r"C:\vicidial-voice-agent_multicampaña\config\textos_audios_amex"

os.makedirs(output_dir, exist_ok=True)

with open(amex_json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for script_id, script_info in data.get("scripts", {}).items():
    # Only generate txt for pre-recorded scripts
    if script_info.get("prerecord"):
        text = script_info.get("text", "")
        file_path = os.path.join(output_dir, f"{script_id}.txt")
        with open(file_path, "w", encoding="utf-8") as out_f:
            out_f.write(text)

print(f"Textos de audios de Amex generados exitosamente en {output_dir}")
