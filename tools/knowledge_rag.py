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
