import subprocess
import time

scripts = [
    "ret_saludo",
    "ret_pedir_cuenta",
    "ret_pedir_titular",
    "ret_motivo_baja",
    "ret_espera",
    "ret_cesion_derechos",
    "ret_entrega_equipo",
    "ret_despedida"
]

for script_id in scripts:
    print(f"=== Grabando: {script_id} ===")
    cmd = ["py", "-3.12", "main.py", "--campania", "retencion", "--mode", "local", "--voice", "grabacion", "--id", script_id]
    subprocess.run(cmd)
    print(f"=== Finalizado: {script_id} ===")
    time.sleep(1) # Pequeña pausa entre ejecuciones

print("Todas las grabaciones han finalizado con éxito.")
