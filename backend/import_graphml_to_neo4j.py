"""
Script para importar archivo GraphML a Neo4j Aura
"""
import xml.etree.ElementTree as ET
from neo4j import GraphDatabase
from config.settings import settings
from loguru import logger
import time

def parse_graphml(file_path):
    """Parsea archivo GraphML y extrae nodos y relaciones"""
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    # Mapeo de atributos
    key_map = {}
    for key in root.findall("{http://graphml.graphdrawing.org/xmlns}key"):
        key_id = key.get("id")
        attr_name = key.get("attr.name")
        key_map[key_id] = attr_name
    
    nodes = []
    edges = []
    
    for node in root.findall("{http://graphml.graphdrawing.org/xmlns}graph/{http://graphml.graphdrawing.org/xmlns}node"):
        node_id = node.get("id")
        node_data = {"id": node_id}
        
        for data in node.findall("{http://graphml.graphdrawing.org/xmlns}data"):
            key_id = data.get("key")
            value = data.text
            if key_id in key_map:
                node_data[key_map[key_id]] = value
        
        nodes.append(node_data)
    
    for edge in root.findall("{http://graphml.graphdrawing.org/xmlns}graph/{http://graphml.graphdrawing.org/xmlns}edge"):
        source = edge.get("source")
        target = edge.get("target")
        edge_data = {"source": source, "target": target}
        
        for data in edge.findall("{http://graphml.graphdrawing.org/xmlns}data"):
            key_id = data.get("key")
            value = data.text
            if key_id in key_map:
                edge_data[key_map[key_id]] = value
        
        edges.append(edge_data)
    
    return nodes, edges

def import_to_neo4j(nodes, edges):
    """Importa nodos y relaciones a Neo4j Aura"""
    uri = settings.NEO4J_URI
    user = settings.NEO4J_USER
    password = settings.NEO4J_PASSWORD
    
    logger.info(f"Conectando a Neo4j: {uri}")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        driver.verify_connectivity()
        logger.info("✅ Conectado a Neo4j Aura")
        
        with driver.session() as session:
            # Limpiar base de datos existente
            logger.info("🗑️ Limpiando base de datos existente...")
            session.run("MATCH (n) DETACH DELETE n")
            
            # Crear nodos
            logger.info(f"📝 Creando {len(nodes)} nodos...")
            for i, node in enumerate(nodes, 1):
                entity_id = node.get("entity_id", node["id"])
                entity_type = node.get("entity_type", "Entity")
                description = node.get("description", "")
                source_id = node.get("source_id", "")
                file_path = node.get("file_path", "")
                created_at = node.get("created_at", "")
                
                query = """
                CREATE (n:Entity {
                    entity_id: $entity_id,
                    entity_type: $entity_type,
                    description: $description,
                    source_id: $source_id,
                    file_path: $file_path,
                    created_at: $created_at
                })
                """
                session.run(query, {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "description": description,
                    "source_id": source_id,
                    "file_path": file_path,
                    "created_at": created_at
                })
                
                if i % 100 == 0:
                    logger.info(f"  Progreso: {i}/{len(nodes)} nodos")
            
            logger.info(f"✅ {len(nodes)} nodos creados")
            
            # Crear relaciones
            logger.info(f"🔗 Creando {len(edges)} relaciones...")
            for i, edge in enumerate(edges, 1):
                source = edge["source"]
                target = edge["target"]
                weight = edge.get("weight", 1.0)
                description = edge.get("description", "")
                keywords = edge.get("keywords", "")
                
                query = """
                MATCH (source:Entity {entity_id: $source})
                MATCH (target:Entity {entity_id: $target})
                CREATE (source)-[r:RELATED {
                    weight: $weight,
                    description: $description,
                    keywords: $keywords
                }]->(target)
                """
                session.run(query, {
                    "source": source,
                    "target": target,
                    "weight": float(weight) if weight else 1.0,
                    "description": description,
                    "keywords": keywords
                })
                
                if i % 100 == 0:
                    logger.info(f"  Progreso: {i}/{len(edges)} relaciones")
            
            logger.info(f"✅ {len(edges)} relaciones creadas")
            
            # Verificar conteo
            result = session.run("MATCH (n) RETURN count(n) as node_count")
            node_count = result.single()["node_count"]
            
            result = session.run("MATCH ()-[r]->() RETURN count(r) as edge_count")
            edge_count = result.single()["edge_count"]
            
            logger.info(f"📊 Total en Neo4j: {node_count} nodos, {edge_count} relaciones")
            
    finally:
        driver.close()
        logger.info("🔌 Conexión cerrada")

def main():
    """Función principal"""
    if not settings.NEO4J_ENABLED:
        logger.error("❌ NEO4J_ENABLED está desactivado. Actívalo en .env")
        return
    
    graphml_path = "docs/knowledge_graph/graph_chunk_entity_relation.graphml"
    
    logger.info(f"📂 Leyendo archivo GraphML: {graphml_path}")
    nodes, edges = parse_graphml(graphml_path)
    
    logger.info(f"📊 Parseado: {len(nodes)} nodos, {len(edges)} relaciones")
    
    logger.info("🚀 Iniciando importación a Neo4j Aura...")
    start_time = time.time()
    
    import_to_neo4j(nodes, edges)
    
    elapsed = time.time() - start_time
    logger.info(f"⏱️ Importación completada en {elapsed:.2f} segundos")

if __name__ == "__main__":
    main()
