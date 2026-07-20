import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger("SiebelCN")

CASOS_NEGOCIO_MAP = {
    "INFO GENERAL DEL SERV": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "INFO GENERAL DEL SERV",
        "SUBMOTIVO": "PRECIOS PRODUCTOS/SERV/ PROMO",
        "SOLUCION": "SE BRINDA INFO",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "TRANSFERENCIA": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "TRANSFERENCIA",
        "SUBMOTIVO": "SE TRANSFIERE LLAMADA",
        "SOLUCION": "TRANSFERENCIA AL AREA CORRESP",
        "MOTIVO CLIENTE": "IZZI MOVIL",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "SE CORTA LLAMADA": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "SE CORTA LLAMADA",
        "SUBMOTIVO": "NO SE LLEGO A UN DIAGNOSTICO",
        "SOLUCION": "SIN DATOS DEL CLIENTE",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "RETENIDO": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "RETENCION",
        "SUBMOTIVO": "RETENIDO EXITO",
        "SOLUCION": "RETENCION EXITOSA",
        "MOTIVO CLIENTE": "PRECIO",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "NO RETENIDO": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "RETENCION",
        "SUBMOTIVO": "NO RETENIDO EXITO",
        "SOLUCION": "RETENCION NO EXITOSA",
        "MOTIVO CLIENTE": "PRECIO",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "DATOS DE LA CUENTA": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "DATOS DE LA CUENTA",
        "SUBMOTIVO": "ACTUALIZACION DE DATOS",
        "SOLUCION": "SE REGISTRA TELEFONO O DATOS DE VISITA TECNICA",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "PERFIL DE PAGO": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "PERFIL DE PAGO",
        "SUBMOTIVO": "BAJA DOMICILIACION TDC",
        "SOLUCION": "SOLICITUD DE BAJA DE TARJETA DE CREDITO/DEBITO",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "NAP SATURADO VALIDACION": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "NAP SATURADO VALIDACION",
        "SUBMOTIVO": "VALIDACION DE DISPONIBILIDAD DE INSTALACION",
        "SOLUCION": "VALIDACION ADMINISTRATIVA DE DISPONIBILIDAD NAP",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    },
    "INCONSISTENCIA": {
        "CATEGORIA": "SERVICIOS",
        "MOTIVO": "INCONSISTENCIA",
        "SUBMOTIVO": "ANOMALIA EN ORDEN DE SERVICIO",
        "SOLUCION": "REPORTADO POR ANOMALIA QUE IMPIDE AVANZAR",
        "MOTIVO CLIENTE": "OTROS",
        "COMENTARIO": "CN GENERADO POR AGENTE IA"
    }
}

def bucleEncuentraItems(driver, xpath, intentos=20, espera=0.5):
    for i in range(intentos):
        try:
            return driver.find_element(By.XPATH, xpath)
        except NoSuchElementException:
            time.sleep(espera)
    logger.warning(f'No se encontró el elemento con xpath: {xpath}')
    return None

def bucleEncuentraItemsShort(driver, xpath, intentos=3, espera=0.5):
    for i in range(intentos):
        try:
            return driver.find_element(By.XPATH, xpath)
        except NoSuchElementException:
            time.sleep(espera)
    return None

def bucleEncuentraItemsClick(driver, xpath):
    contador = 0
    while contador < 20:
        try:
            el = driver.find_element(By.XPATH, xpath)
            el.click()
            time.sleep(0.5)
            return True
        except Exception:
            contador += 1
            time.sleep(0.5)
    return False

def desbloquearColumna(driver):
    logger.info("Validando bloqueo de columna...")
    estado_col = ""
    intento = 0
    while intento < 3:
        try:
            estado_col = bucleEncuentraItemsShort(driver, "//div[@id='jqgh_s_12_l_Status' and contains(text(),'Estado')]")
            if estado_col:
                break
        except TimeoutException:
            pass
        
        intento += 1
        try:
            td = bucleEncuentraItems(driver, "//td[@aria-roledescription='Fecha de apertura' and @id='1_s_12_l_Created']")
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].focus();", td)
            td.click()
            time.sleep(0.3)
            for i in range(4):
                driver.switch_to.active_element.send_keys(Keys.TAB)
        except:
            pass

    try:
        bloqueado = len(estado_col.find_elements(By.XPATH, ".//span[contains(@class, 'siebui-col-lock')]")) > 0
    except Exception:
        bloqueado = False

    if bloqueado:
        logger.info("🔒 Columna 'Estado' bloqueada. Iniciando desbloqueo...")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", estado_col)
        ActionChains(driver).move_to_element(estado_col).pause(0.2).click().perform()
        
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//li[@rn='unlockColumn']")))
            desbloquear_btn = driver.execute_script("""
                const menus = Array.from(document.querySelectorAll("ul[ot='headerMenu']"));
                if (!menus.length) return null;
                const visibleMenus = menus.filter(m => getComputedStyle(m).display !== 'none');
                if (!visibleMenus.length) return null;
                visibleMenus.sort((a,b) => (parseInt(getComputedStyle(b).zIndex)||0) - (parseInt(getComputedStyle(a).zIndex)||0));
                return visibleMenus[0].querySelector("li[rn='unlockColumn'] a.siebui-icon-unlock") || null;
            """)
            if desbloquear_btn:
                driver.execute_script("""
                    const el = arguments[0];
                    el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    el.click();
                """, desbloquear_btn)
                logger.info("✅ Columna desbloqueada correctamente.")
                bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Estado' and starts-with(@id, '1_s_12_l_')]")
        except Exception as e:
            logger.error(f"⚠️ Error al intentar desbloquear columna: {e}")
    else:
        logger.info("🔓 Columna 'Estado' desbloqueada.")

def llenar_y_cerrar_CN(driver, tipo_caso: str):
    """
    Llena el caso de negocio y lo cierra, basándose en la configuración de `tipo_caso`.
    Retorna True si tuvo éxito, False en caso contrario.
    """
    valores = CASOS_NEGOCIO_MAP.get(tipo_caso)
    if not valores:
        # Default de seguridad si envían algo no mapeado
        valores = CASOS_NEGOCIO_MAP["INFO GENERAL DEL SERV"]
        logger.warning(f"Tipo de caso '{tipo_caso}' no encontrado. Usando por defecto.")

    logger.info("Creando nuevo Caso de Negocio...")
    bucleEncuentraItemsClick(driver, "//button[@title='Casos de negocio Applet de lista:Nuevo' and @aria-label='Casos de negocio Applet de lista:Nuevo']")
    time.sleep(5)
    desbloquearColumna(driver)
    time.sleep(3)
    
    logger.info("Llenando campos del CN...")
    
    # Categoria
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Categoría' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//input[@un='Categoría' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["CATEGORIA"])
    except: pass
    
    # Motivo
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Motivos' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//input[@un='Motivos' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["MOTIVO"])
    except: pass
    
    # Submotivo
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Submotivo' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//input[@un='Submotivo' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["SUBMOTIVO"])
    except: pass
    
    # Solucion
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Solución' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//input[@un='Solución' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["SOLUCION"])
    except: pass
    
    # Comentarios
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Comentarios' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//textarea[@un='Comentarios' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["COMENTARIO"])
    except: pass
    
    time.sleep(3)
    
    # Motivo Cliente
    try:
        bucleEncuentraItemsClick(driver, "//td[@aria-roledescription='Motivo Cliente' and starts-with(@id, '1_s_12_l_')]")
        inp = bucleEncuentraItems(driver, "//input[@un='Motivo Cliente' and starts-with(@aria-labelledby, 's_12_l_')]")
        inp.clear()
        inp.send_keys(valores["MOTIVO CLIENTE"])
    except: pass
    
    # Click en el link del Caso de Negocio generado
    logger.info("Entrando al detalle del CN...")
    try:
        wait = WebDriverWait(driver, 10)
        elemento = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[@aria-roledescription='Caso de negocio' and starts-with(@id, '1_s_12_l_')]//a")))
        try:
            elemento.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", elemento)
    except Exception as e:
        logger.error(f"❌ Error al entrar al CN: {e}")
        # Limpiar alertas
        driver.execute_script("""
            window._capturedAlerts = [];
        """)
        return False

    # Cerrar CN
    logger.info("Cerrando el CN...")
    time.sleep(2)
    try:
        driver.find_element(By.XPATH, "//input[@aria-label='Motivo del cierre']").click()
        inp = driver.find_element(By.XPATH, "//input[@aria-label='Motivo del cierre']")
        inp.send_keys("RAC INFORMA Y SOLUCIONA")
        inp.send_keys(Keys.ENTER)
        
        inp_status = bucleEncuentraItems(driver, '/html/body/div[1]/div/div[5]/div/div[8]/div[2]/div[1]/div/div[3]/div[1]/div/form/div/span/div[3]/div/div/table/tbody/tr[3]/td[8]/div/input')
        if not inp_status:
            # Alternativa xpath
            inp_status = driver.find_element(By.XPATH, "//input[@rn='Status' and @un='Estado']")
            
        inp_status.click()
        time.sleep(0.1)
        for _ in range(10):
            inp_status.send_keys(Keys.BACKSPACE)
            time.sleep(0.05)
        
        inp_status.send_keys("Cerrado")
        inp_status.send_keys(Keys.ENTER)
        
        # Guardar
        bucleEncuentraItemsClick(driver, '/html/body/div[1]/div/div[5]/div/div[8]/div[2]/div[1]/div/div[3]/div[1]/div/form/div/span/div[1]/div[3]/button[2]')
        logger.info("✅ Caso de negocio llenado y cerrado exitosamente.")
        return True
    except Exception as e:
        logger.error(f"Error al cerrar CN: {e}")
        return False
