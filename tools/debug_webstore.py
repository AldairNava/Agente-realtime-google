"""
Script de diagnóstico para interactuar con la Chrome Web Store y encontrar el botón de instalación.
Ejecutar: py -3.12 tools/debug_webstore.py
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

URL = "https://chromewebstore.google.com/detail/rpa-extension/ccilojpjnmepojkjkdpohdkbjpkfoojd"

opts = Options()
opts.add_argument("--no-sandbox")
opts.add_argument("--start-maximized")
opts.add_experimental_option("excludeSwitches", ["enable-logging"])

driver = webdriver.Chrome(options=opts)
print(f"Navegando a {URL}...")
driver.get(URL)

print("Esperando 7s para renderizado JS...")
time.sleep(7)

# Buscar todos los elementos button
btns = driver.find_elements(By.TAG_NAME, "button")
print(f"\n[DIAG] Botones encontrados por etiqueta <button> ({len(btns)}):")
for i, btn in enumerate(btns):
    try:
        txt = btn.text.strip()
        cls = btn.get_attribute("class") or ""
        span_text = ""
        try:
            spans = btn.find_elements(By.TAG_NAME, "span")
            span_text = " | ".join([s.text.strip() for s in spans if s.text.strip()])
        except Exception:
            pass
        print(f"  [{i}] text='{txt}' | class='{cls[:50]}' | spans='{span_text}'")
    except Exception as e:
        print(f"  [{i}] Error: {e}")

# Buscar todos los elementos div con rol button o texto
divs = driver.find_elements(By.XPATH, "//*[@role='button']")
print(f"\n[DIAG] Elementos con role='button' ({len(divs)}):")
for i, div in enumerate(divs):
    try:
        txt = div.text.strip().replace('\n', ' ')
        cls = div.get_attribute("class") or ""
        print(f"  [{i}] text='{txt[:50]}' | class='{cls[:50]}'")
    except Exception as e:
        print(f"  [{i}] Error: {e}")

# Buscar texto con XPATH que contenga "Agregar" o "Add"
elements = driver.find_elements(By.XPATH, "//*[contains(text(),'Agregar') or contains(text(),'Add') or contains(text(),'Chrome') or contains(text(),'chrome')]")
print(f"\n[DIAG] Elementos con texto 'Agregar', 'Add' o 'Chrome' ({len(elements)}):")
for i, el in enumerate(elements[:20]):
    try:
        txt = el.text.strip().replace('\n', ' ')
        print(f"  [{i}] tag={el.tag_name} | text='{txt[:80]}'")
    except Exception as e:
        pass

print("\nDiagnóstico terminado. Deja abierto el navegador para revisar visualmente. Ctrl+C para cerrar.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    driver.quit()
