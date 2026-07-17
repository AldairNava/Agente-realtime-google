import json
import logging
import os

logger = logging.getLogger(__name__)

class KnowledgeRAG:
    """Motor de Búsqueda sobre Documentos Corporativos (Manuales Call Center)"""
    def __init__(self, directory="knowledge"):
        self.directory = directory
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.knowledge_path = os.path.join(self.base_dir, self.directory)
        self.db = {}
        self._load_all()

    def _load_all(self):
        """Carga y fusiona todos los archivos JSON en la carpeta de conocimiento."""
        if not os.path.exists(self.knowledge_path):
            logger.warning(f"La carpeta de conocimiento no existe: {self.knowledge_path}")
            return

        for filename in os.listdir(self.knowledge_path):
            if filename.endswith(".json"):
                path = os.path.join(self.knowledge_path, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.db[filename] = data  # Guardamos por archivo para contexto
                        logger.info(f"✅ Cargado conocimiento de: {filename}")
                except Exception as e:
                    logger.error(f"Error cargando {filename}: {e}")

    def _search_recursive(self, data, query, results):
        """Busca recursivamente el término en diccionarios, listas y textos."""
        # 🟢 NUEVO: Si la data es un string, buscar el término directamente
        if isinstance(data, str):
            if query in data.lower():
                results.append(data)
            return

        if isinstance(data, dict):
            for k, v in data.items():
                # Buscar en la llave
                if query in str(k).lower():
                    results.append(f"{k}: {v}")
                # Buscar en el valor (recursión)
                self._search_recursive(v, query, results)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, str) and query in item.lower():
                    results.append(item)
                self._search_recursive(item, query, results)

    def consultar_datos_mundial_2026(self, tema: str) -> str:
        """
        Consulta la base de datos OFICIAL del Mundial 2026. 
        ÚSALA SIEMPRE que el cliente pregunte por fechas, estadios, partidos, canales de TV o cualquier dato técnico.
        """
        logger.info(f"[RAG Engine] Consultando datos oficiales para: {tema}")
        
        # Búsqueda por palabras clave para mayor flexibilidad
        keywords = [k for k in tema.lower().split() if len(k) > 3]
        if not keywords: # Si la palabra es muy corta, usamos el tema completo
            keywords = [tema.lower()]
            
        results = []
        for word in keywords:
            self._search_recursive(self.db, word, results)
        
        if results:
            unique_results = list(set([str(r) for r in results]))
            return "RESULTADOS OFICIALES ENCONTRADOS:\n- " + "\n- ".join(unique_results[:8])
            
        return f"No tengo información específica sobre '{tema}' en mi base de datos del Mundial. Menciona que debemos estar atentos a los comunicados oficiales de la FIFA."

    def consultar_catalogo_amex(self, consulta: str) -> str:
        """
        Busca tarjetas en el catálogo de American Express.
        Si la consulta incluye el ingreso mensual (ej. '60000', '40 mil'), buscará qué tarjetas están disponibles para ese nivel de ingresos.
        Si el cliente pide una tarjeta por nombre, la buscará por nombre.
        SIEMPRE invoca esta herramienta después de obtener los ingresos del cliente en el nodo 3.
        """
        logger.info(f"[RAG Engine] Consultando catálogo AMEX para: {consulta}")
        
        amex_data = self.db.get("amex_catalog.json", [])
        if not amex_data:
            return "Error: No se encontró el catálogo de AMEX en la base de datos RAG."
            
        import re
        # Extraer números de la consulta si existen
        numeros = re.findall(r'\d+', consulta.replace(',', '').replace('.', ''))
        ingreso = None
        if numeros:
            ingreso_bruto = int(numeros[0])
            # Si dicen "60" y la palabra "mil", asume 60,000
            if ingreso_bruto < 1000 and ("mil" in consulta.lower() or "k" in consulta.lower()):
                ingreso_bruto *= 1000
            elif ingreso_bruto >= 1000:
                ingreso = ingreso_bruto
                
        resultados = []
        if ingreso is not None:
            # Búsqueda por ingresos
            for tarjeta in amex_data:
                if isinstance(tarjeta, dict) and "ingreso_minimo_mensual" in tarjeta:
                    if ingreso >= tarjeta["ingreso_minimo_mensual"]:
                        resultados.append(tarjeta)
        else:
            # Búsqueda por texto (nombre de tarjeta o palabra clave)
            for tarjeta in amex_data:
                if isinstance(tarjeta, dict):
                    texto_tarjeta = json.dumps(tarjeta, ensure_ascii=False).lower()
                    if consulta.lower() in texto_tarjeta:
                        resultados.append(tarjeta)
                        
        if resultados:
            respuesta = f"Tarjetas disponibles encontradas para la consulta '{consulta}':\n"
            for r in resultados:
                respuesta += f"- Nombre: {r.get('nombre_tarjeta', 'Tarjeta')} (ID_SISTEMA: {r.get('id_sistema', '')})\n  Ingreso Mínimo: ${r.get('ingreso_minimo_mensual', 0)}\n  Cashback: {r.get('cashback', '')}\n  Bono Amazon: {r.get('bono_amazon', '')}\n  Beneficios: {r.get('beneficios', '')}\n\n"
            return respuesta
        else:
            if ingreso is not None:
                return f"El ingreso de ${ingreso} no es suficiente para ninguna de nuestras tarjetas (el mínimo es $15,000)."
            return f"No se encontraron tarjetas que coincidan con la búsqueda: '{consulta}'."

    def consultar_informacion_plata(self, tema: str) -> str:
        """
        Consulta información técnica y reglas de negocio EXCLUSIVAS de la campaña Plata Card.
        Úsalo cuando el cliente pregunte por cashback, meses sin intereses (MSI), tasas, CAT, comisiones, 60 días para pagar, retiros, requisitos, o beneficios Mastercard.
        """
        logger.info(f"[RAG Engine] Consultando información de Plata Card para: {tema}")
        
        plata_data = self.db.get("plata_knowledge.json", {})
        if not plata_data:
            return "Error: No se encontró la base de conocimiento de Plata Card."
            
        # Búsqueda por palabras clave
        keywords = [k.lower().strip('¿?.,') for k in tema.split() if len(k) > 3]
        if not keywords:
            keywords = [tema.lower()]
            
        # Primero buscar coincidencias fuertes en las llaves
        mejores_matches = []
        for key, value in plata_data.items():
            for word in keywords:
                if word in key.lower() or word in value.lower():
                    if value not in mejores_matches:
                        mejores_matches.append(value)
                        
        if mejores_matches:
            # Retornar los primeros 3 matches para no exceder contexto
            return "INFORMACIÓN OFICIAL PLATA CARD:\n\n" + "\n\n".join(mejores_matches[:3])
            
        return f"No encontré información específica sobre '{tema}' en el manual de Plata Card. Por favor, ofrece transferir la llamada con un compañero para resolver la duda detalladamente."
