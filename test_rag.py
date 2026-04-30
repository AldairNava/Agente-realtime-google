import os
import sys
import json
import logging

# Configurar logging básico
logging.basicConfig(level=logging.INFO)

# Añadir el directorio actual al path para importar tools
sys.path.append(os.getcwd())

from tools.knowledge_rag import KnowledgeRAG

def test_rag():
    print("--- Iniciando Prueba de RAG Recursivo ---")
    rag = KnowledgeRAG(directory="knowledge")
    
    queries = ["inauguración", "televisa", "metlife", "final", "monterrey", "broadcasters"]
    
    for q in queries:
        print(f"\n--- Buscando: '{q}' ---")
        try:
            res = rag.consultar_datos_mundial_2026(q)
            print(f"Resultado:\n{res}")
        except Exception as e:
            print(f"Error buscando '{q}': {e}")

if __name__ == "__main__":
    test_rag()
