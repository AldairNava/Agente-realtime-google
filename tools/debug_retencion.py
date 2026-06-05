"""
Script de diagnóstico — inspecciona el DOM post-login del portal de Retención.
Ejecutar: py -3.12 tools/debug_retencion.py
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

BASE_URL = "https://retencion-rpa.izzi.local"
LOGIN_URL = f"{BASE_URL}/log-in?"
USERNAME  = "p-ccorrea"
PASSWORD  = "Crisco960427$"

opts = Options()
opts.add_argument("--ignore-certificate-errors")
opts.add_argument("--ignore-ssl-errors")
opts.add_argument("--allow-insecure-localhost")
opts.add_argument("--no-sandbox")
opts.add_argument("--start-maximized")
opts.add_experimental_option("excludeSwitches", ["enable-logging"])

driver = webdriver.Chrome(options=opts)
driver.get(LOGIN_URL)
time.sleep(3)

# --- Cerrar modal extensión ---
try:
    btns = driver.find_elements(By.XPATH, "//*[contains(@class,'modal')]//button | //*[contains(@class,'close')]")
    for b in btns:
        if b.is_displayed():
            print(f"[MODAL] Cerrando botón: '{b.text}' class='{b.get_attribute('class')}'")
            b.click()
            time.sleep(0.5)
            break
except Exception as e:
    print(f"[MODAL] Error: {e}")

time.sleep(1)

# --- Llenar login ---
inputs = driver.find_elements(By.TAG_NAME, "input")
print(f"\n[LOGIN] Inputs encontrados en página de login: {len(inputs)}")
for i, inp in enumerate(inputs):
    print(f"  [{i}] type={inp.get_attribute('type')} | placeholder='{inp.get_attribute('placeholder')}' | name='{inp.get_attribute('name')}' | id='{inp.get_attribute('id')}' | class='{inp.get_attribute('class')[:40]}'")

text_inputs = [i for i in inputs if i.get_attribute("type") in ("text", "email", None, "") and i.is_displayed()]
pass_inputs = [i for i in inputs if i.get_attribute("type") == "password" and i.is_displayed()]

if text_inputs:
    text_inputs[0].clear()
    text_inputs[0].send_keys(USERNAME)
    print(f"\n[LOGIN] Usuario escrito en input[0]: '{text_inputs[0].get_attribute('placeholder')}'")

if pass_inputs:
    pass_inputs[0].clear()
    pass_inputs[0].send_keys(PASSWORD)
    print(f"[LOGIN] Contraseña escrita en input password")

# Clic en botón Iniciar sesion
btns = driver.find_elements(By.TAG_NAME, "button")
print(f"\n[LOGIN] Botones encontrados: {len(btns)}")
for i, b in enumerate(btns):
    print(f"  [{i}] text='{b.text}' | type='{b.get_attribute('type')}' | class='{b.get_attribute('class')[:40]}'")

btn_login = None
for b in btns:
    txt = b.text.lower()
    if "iniciar" in txt or "ingresar" in txt or "sesion" in txt or "login" in txt:
        btn_login = b
        break

if btn_login:
    # Usar JS click para evitar intercepción del modal
    driver.execute_script("arguments[0].click();", btn_login)
    print(f"\n[LOGIN] Clic JS en botón: '{btn_login.text}'")
else:
    if pass_inputs:
        pass_inputs[0].send_keys(Keys.RETURN)
    print("\n[LOGIN] Fallback: Enter en password")

print("\n[POST-CLICK] Monitoreando URL y errores por 15 segundos...")
for i in range(15):
    time.sleep(1)
    url = driver.current_url
    title = driver.title

    # Buscar mensajes de error visibles
    error_msgs = []
    for sel in [".alert", ".error", ".toast", "[class*='error']", "[class*='alert']", "[class*='danger']"]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                txt = el.text.strip()
                if txt:
                    error_msgs.append(f"{sel}: '{txt}'")
        except Exception:
            pass

    print(f"  [{i+1}s] URL: {url} | Title: {title}" + (f" | ERRORES: {error_msgs}" if error_msgs else ""))

    if "/log-in" not in url:
        print(f"\n✅ LOGIN EXITOSO! URL cambió a: {url}")
        break

print(f"\n[FINAL] URL: {driver.current_url}")
print(f"[FINAL] Título: {driver.title}")

# Inspección final del DOM
inputs_post = driver.find_elements(By.TAG_NAME, "input")
print(f"[FINAL] Inputs: {len(inputs_post)}")
for i, inp in enumerate(inputs_post):
    ph = inp.get_attribute("placeholder") or ""
    nm = inp.get_attribute("name") or ""
    print(f"  [{i}] type='{inp.get_attribute('type')}' | name='{nm}' | placeholder='{ph}' | visible={inp.is_displayed()}")

# Textos visibles
print("\n[FINAL] Textos visibles:")
count = 0
for d in driver.find_elements(By.XPATH, "//*[normalize-space(text())]"):
    txt = d.text.strip()
    if txt and len(txt) < 100 and d.is_displayed():
        print(f"  {d.tag_name}: '{txt}'")
        count += 1
        if count >= 25:
            break


print("\n[DIAG] Diagnóstico completo. Revisa la salida y el navegador.")
print("[DIAG] Presiona Ctrl+C cuando termines de revisar.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    driver.quit()
    print("[DIAG] Navegador cerrado.")
