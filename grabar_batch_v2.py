import subprocess
import time

scripts = [
    "ret_saludo_v2", "ret_saludo_v3",
    "ret_pedir_cuenta_v2", "ret_pedir_cuenta_v3",
    "ret_pedir_titular_v2", "ret_pedir_titular_v3",
    "ret_motivo_baja_v2", "ret_motivo_baja_v3",
    "ret_espera_v2", "ret_espera_v3",
    "ret_cesion_derechos_v2", "ret_cesion_derechos_v3",
    "ret_entrega_equipo_v2", "ret_entrega_equipo_v3",
    "ret_despedida_v2", "ret_despedida_v3"
]

for script_id in scripts:
    print(f"=== Grabando: {script_id} ===")
    cmd = ["py", "-3.12", "main.py", "--campania", "retencion", "--mode", "local", "--voice", "grabacion", "--id", script_id]
    subprocess.run(cmd)
    print(f"=== Finalizado: {script_id} ===")
    time.sleep(1)

print("Todas las variaciones se han grabado con éxito.")
