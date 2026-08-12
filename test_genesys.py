from pywinauto.application import Application
import time

def main():
    import pythoncom
    pythoncom.CoInitialize()

    print("Conectando a Genesys...")
    try:
        app = Application(backend="uia").connect(path="InteractionWorkspace.exe", timeout=2)
        print("Conectado a:", app)
    except Exception as e:
        print("Error al conectar:", e)
        return
    
    main_window = None
    for w in app.windows():
        title = w.texts()[0] if w.texts() else ""
        print(f"Ventana encontrada: '{title}'")
        if "workspace" in title.lower():
            main_window = w
            break

    if not main_window:
        print("No se encontro ventana de workspace. Usando la primera ventana.")
        if app.windows():
            main_window = app.windows()[0]
        else:
            return
        
    print("=== OBTENIENDO TEXTOS DE DESCENDIENTES ===")
    try:
        descendants = main_window.descendants()
        texts = []
        for d in descendants:
            try:
                for t in d.texts():
                    if t and t.strip() and t.strip() not in texts:
                        texts.append(t.strip())
            except Exception:
                pass
                
        print("Textos únicos encontrados:")
        print(" | ".join(texts))
    except Exception as e:
        print("Error obteniendo descendientes:", e)
    
if __name__ == "__main__":
    main()
