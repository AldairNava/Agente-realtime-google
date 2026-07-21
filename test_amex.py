import sys
import time
import logging
import threading
import os
from tools.amex_form import AMEXFormHandler

logging.basicConfig(level=logging.INFO)

handler = AMEXFormHandler(client_phone='5551234567', vicidial_user='test_user')
handler.guardar_dato_cliente('nombre', 'Aldair')
handler.guardar_dato_cliente('apellido_paterno', 'Nava')
handler.guardar_dato_cliente('apellido_materno', 'Martínez')
handler.guardar_dato_cliente('dia_nacimiento', '21')
handler.guardar_dato_cliente('mes_nacimiento', 'mayo')
handler.guardar_dato_cliente('anio_nacimiento', '1991')

print("=== INICIANDO PRUEBA DEL NAVEGADOR ===")
print("Iniciando formulario...")
resultado = handler.iniciar_llenado_formulario_amex('gold_card')
print(f"Resultado: {resultado}")

def simular_ai():
    time.sleep(15)
    print("\n[IA Simulada] Confirmando RFC...")
    handler.confirmar_rfc_amex(True)
    
    time.sleep(2)
    print("[IA Simulada] Proveendo Email...")
    handler.proveer_dato_faltante_amex('email', 'prueba@gmail.com')
    
    time.sleep(2)
    print("[IA Simulada] Proveendo Celular...")
    handler.proveer_dato_faltante_amex('celular', '5512345678')
    
    time.sleep(2)
    print("[IA Simulada] Proveendo CP...")
    handler.proveer_dato_faltante_amex('codigo_postal', '11000')
    
    time.sleep(2)
    print("[IA Simulada] Proveendo TDC...")
    handler.proveer_dato_faltante_amex('tiene_tdc', 'si')
    
    time.sleep(2)
    print("[IA Simulada] Proveendo Auto...")
    handler.proveer_dato_faltante_amex('tiene_auto', 'no')
    
    time.sleep(2)
    print("[IA Simulada] Proveendo Hipoteca...")
    handler.proveer_dato_faltante_amex('tiene_hipoteca', 'no')
    
    time.sleep(5)
    print("[IA Simulada] Llamada terminada, colgando...")
    with open(os.path.join(handler.sync_dir, 'call_ended.txt'), 'w', encoding='utf-8') as f:
        f.write("ended")

threading.Thread(target=simular_ai, daemon=True).start()

print("El navegador deberia aparecer en pantalla y auto-llenarse. Esperando 120 segundos...")
time.sleep(120)
print("=== PRUEBA TERMINADA ===")
