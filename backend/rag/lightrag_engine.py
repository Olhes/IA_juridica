import asyncio
from typing import Dict, List, Any, Optional
import json
from pathlib import Path
from loguru import logger

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.llm import gpt_4o_complete, gpt_4o_mini_complete
    from lightrag.utils import EmbeddingFunc
    LIGHTRAG_AVAILABLE = True
except ImportError:
    logger.warning("LightRAG no disponible. Usando implementación simulada.")
    LIGHTRAG_AVAILABLE = False

class LegalRAGEngine:
    """Motor RAG especializado para documentos legales con LightRAG"""
    
    def __init__(self, working_dir: str = "./docs/knowledge_graph"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        if LIGHTRAG_AVAILABLE:
            self._initialize_lightrag()
        else:
            self.documents = {}  # Implementación fallback
            self.embeddings = {}
        
        logger.info(f"LegalRAG Engine inicializado en {working_dir}")
    
    def _initialize_lightrag(self):
        """Inicializa LightRAG con configuración para documentos legales"""
        
        # Configurar función de embedding
        async def embedding_func(texts: List[str]) -> List[List[float]]:
            """Función de embedding para textos legales"""
            # Aquí usarías un modelo de embeddings real
            # Por ahora, simulación simple
            import hashlib
            embeddings = []
            for text in texts:
                # Simulación de embedding basado en hash
                hash_obj = hashlib.md5(text.encode())
                # Convertir a vector de 768 dimensiones (tamaño típico)
                embedding = [float(int(hash_obj.hexdigest()[i:i+2], 16)) / 255.0 
                           for i in range(0, min(1536, len(hash_obj.hexdigest())), 2)]
                # Rellenar o truncar a 768 dimensiones
                while len(embedding) < 768:
                    embedding.append(0.0)
                embeddings.append(embedding[:768])
            return embeddings
        
        # Configurar función LLM
        async def llm_func(prompt: str, **kwargs) -> str:
            """Función LLM para procesamiento"""
            # Aquí integrarías con OpenAI u otro LLM
            # Por ahora, respuesta simulada
            return f"Respuesta LLM para: {prompt[:100]}..."
        
        # Inicializar LightRAG
        self.rag = LightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=768,
                max_token_size=8192,
                func=embedding_func
            )
        )
        
        logger.info("LightRAG inicializado correctamente")
    
    async def add_document(self, content: str, metadata: Dict[str, Any], document_id: str):
        """Agrega un documento al sistema RAG"""
        
        try:
            if LIGHTRAG_AVAILABLE:
                await self.rag.ainsert(content)
                logger.info(f"Documento {document_id} agregado a LightRAG")
            else:
                # Implementación fallback
                self.documents[document_id] = {
                    "content": content,
                    "metadata": metadata,
                    "chunks": self._chunk_content(content)
                }
                logger.info(f"Documento {document_id} guardado localmente")
                
        except Exception as e:
            logger.error(f"Error agregando documento {document_id}: {str(e)}")
            raise
    
    async def query(self, question: str, param: str = "Similarity") -> Dict[str, Any]:
        """
        Realiza una consulta al sistema RAG
        
        Args:
            question: Pregunta del usuario
            param: Tipo de consulta (Similarity, Naive, Local)
            
        Returns:
            Dict con respuesta y fuentes
        """
        
        try:
            if LIGHTRAG_AVAILABLE:
                # Usar LightRAG real
                result = await self.rag.aquery(
                    question, 
                    param=QueryParam(mode=param)
                )
                
                return {
                    "answer": result,
                    "sources": self._extract_sources_from_result(result),
                    "confidence": self._calculate_confidence(result),
                    "method": "lightrag"
                }
            else:
                # Implementación fallback simple
                return await self._fallback_query(question)
                
        except Exception as e:
            logger.error(f"Error en consulta RAG: {str(e)}")
            return {
                "answer": "No se pudo procesar la consulta en este momento.",
                "sources": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    async def _fallback_query(self, question: str) -> Dict[str, Any]:
        """Implementación fallback de consulta"""
        
        best_match = None
        best_score = 0.0
        
        question_lower = question.lower()
        
        # Búsqueda simple por palabras clave
        for doc_id, doc_data in self.documents.items():
            content = doc_data["content"].lower()
            
            # Calcular similitud simple
            common_words = set(question_lower.split()) & set(content.split())
            score = len(common_words) / max(len(set(question_lower.split())), 1)
            
            if score > best_score:
                best_score = score
                best_match = doc_data
        
        if best_match and best_score > 0.1:
            # Extraer fragmento relevante
            relevant_text = self._extract_relevant_fragment(
                best_match["content"], 
                question
            )
            
            return {
                "answer": f"Basado en los documentos disponibles: {relevant_text[:500]}...",
                "sources": [best_match["metadata"].get("filename", "Unknown")],
                "confidence": best_score,
                "method": "fallback_keyword"
            }
        else:
            return {
                "answer": "No se encontró información relevante en los documentos procesados.",
                "sources": [],
                "confidence": 0.0,
                "method": "fallback_no_match"
            }
    
    def _chunk_content(self, content: str, chunk_size: int = 1000) -> List[str]:
        """Divide el contenido en chunks"""
        
        chunks = []
        sentences = content.split('. ')
        
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk + sentence) < chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _extract_relevant_fragment(self, content: str, question: str) -> str:
        """Extrae fragmento relevante del contenido"""
        
        question_words = set(question.lower().split())
        sentences = content.split('. ')
        
        best_sentence = ""
        best_score = 0
        
        for sentence in sentences:
            sentence_words = set(sentence.lower().split())
            common_words = question_words & sentence_words
            score = len(common_words) / max(len(question_words), 1)
            
            if score > best_score and len(sentence) > 50:
                best_score = score
                best_sentence = sentence
        
        return best_sentence if best_sentence else content[:300]
    
    def _extract_sources_from_result(self, result: str) -> List[str]:
        """Extrae fuentes del resultado de LightRAG"""
        # Implementación básica - LightRAG debería incluir fuentes
        return ["Fuente no especificada"]
    
    def _calculate_confidence(self, result: str) -> float:
        """Calcula confianza en el resultado"""
        # Implementación básica
        if len(result) > 100:
            return 0.8
        elif len(result) > 50:
            return 0.6
        else:
            return 0.4
    
    async def rebuild_index(self):
        """Reconstruye el índice RAG"""
        
        try:
            if LIGHTRAG_AVAILABLE:
                # LightRAG maneja el índice automáticamente
                logger.info("Índice LightRAG reconstruido")
            else:
                # Para implementación fallback, no hay índice que reconstruir
                logger.info("No hay índice que reconstruir en modo fallback")
                
        except Exception as e:
            logger.error(f"Error reconstruyendo índice: {str(e)}")
            raise
    
    async def get_knowledge_graph(self) -> Dict[str, Any]:
        """Obtiene datos del grafo de conocimiento para visualización"""
        
        try:
            if LIGHTRAG_AVAILABLE:
                # Extraer grafo de LightRAG
                graph_data = await self.rag.graph_storage.get_all_edges()
                
                # Formatear para visualización
                nodes = []
                edges = []
                
                for edge in graph_data:
                    nodes.extend([
                        {"id": edge.source, "label": edge.source},
                        {"id": edge.target, "label": edge.target}
                    ])
                    edges.append({
                        "source": edge.source,
                        "target": edge.target,
                        "label": edge.label
                    })
                
                return {
                    "nodes": nodes,
                    "edges": edges,
                    "total_nodes": len(nodes),
                    "total_edges": len(edges)
                }
            else:
                # Implementación fallback
                return {
                    "nodes": [],
                    "edges": [],
                    "total_nodes": 0,
                    "total_edges": 0,
                    "message": "Modo fallback - sin grafo disponible"
                }
                
        except Exception as e:
            logger.error(f"Error obteniendo grafo de conocimiento: {str(e)}")
            return {
                "nodes": [],
                "edges": [],
                "error": str(e)
            }
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """Lista todos los documentos en el sistema"""
        
        if LIGHTRAG_AVAILABLE:
            # Obtener documentos de LightRAG
            try:
                docs = await self.rag.doc_storage.get_all_documents()
                return [
                    {
                        "id": doc.get("id", "unknown"),
                        "title": doc.get("title", "Untitled"),
                        "metadata": doc.get("metadata", {}),
                        "added_date": doc.get("added_date", "unknown")
                    }
                    for doc in docs
                ]
            except:
                pass
        
        # Fallback - listar documentos locales
        documents = []
        for doc_id, doc_data in self.documents.items():
            documents.append({
                "id": doc_id,
                "title": doc_data["metadata"].get("title", doc_id),
                "metadata": doc_data["metadata"],
                "content_length": len(doc_data["content"]),
                "chunks_count": len(doc_data["chunks"])
            })
        
        return documents
    
    async def delete_document(self, document_id: str) -> bool:
        """Elimina un documento del sistema"""
        
        try:
            if LIGHTRAG_AVAILABLE:
                # Implementar eliminación en LightRAG
                # Por ahora, solo fallback
                pass
            
            if document_id in self.documents:
                del self.documents[document_id]
                logger.info(f"Documento {document_id} eliminado")
                return True
            else:
                logger.warning(f"Documento {document_id} no encontrado")
                return False
                
        except Exception as e:
            logger.error(f"Error eliminando documento {document_id}: {str(e)}")
            return False
    
    async def search_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """Búsqueda por palabra clave"""
        
        results = []
        keyword_lower = keyword.lower()
        
        for doc_id, doc_data in self.documents.items():
            content = doc_data["content"].lower()
            
            if keyword_lower in content:
                # Extraer fragmentos relevantes
                fragments = []
                for chunk in doc_data["chunks"]:
                    if keyword_lower in chunk.lower():
                        fragments.append(chunk[:200] + "..." if len(chunk) > 200 else chunk)
                
                results.append({
                    "document_id": doc_id,
                    "title": doc_data["metadata"].get("title", doc_id),
                    "fragments": fragments[:3],  # Limitar a 3 fragmentos
                    "relevance": content.count(keyword_lower)
                })
        
        # Ordenar por relevancia
        results.sort(key=lambda x: x["relevance"], reverse=True)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del sistema RAG"""
        
        stats = {
            "total_documents": len(self.documents),
            "total_chunks": sum(len(doc["chunks"]) for doc in self.documents.values()),
            "lightrag_available": LIGHTRAG_AVAILABLE,
            "working_directory": str(self.working_dir),
            "documents_by_type": {}
        }
        
        # Agrupar por tipo de documento
        for doc_id, doc_data in self.documents.items():
            doc_type = doc_data["metadata"].get("document_type", "unknown")
            stats["documents_by_type"][doc_type] = stats["documents_by_type"].get(doc_type, 0) + 1
        
        return stats
