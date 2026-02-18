import asyncio
from typing import Dict, List, Any, Optional
import json
from pathlib import Path
from loguru import logger

from config.settings import settings

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    logger.warning("Cohere SDK no disponible")
    COHERE_AVAILABLE = False

try:
    from lightrag import LightRAG, QueryParam
    from lightrag.utils import EmbeddingFunc
    LIGHTRAG_AVAILABLE = True
except Exception as e:
    logger.warning(f"LightRAG no disponible: {e}")
    LIGHTRAG_AVAILABLE = False


class LegalRAGEngine:
    """Motor RAG especializado para documentos legales con LightRAG + Cohere"""
    
    _DOCUMENTS_STORE_FILENAME = "documents_store.json"
    
    def __init__(self, working_dir: str = "./docs/knowledge_graph"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
    
        self.documents = {}
        self.embeddings = {}
        self.rag = None
        self._storages_initialized = False
        
        # Cargar documentos persistidos del disco
        self._load_documents_from_disk()
        
        # Inicializar cliente Cohere
        self.cohere_client = None
        if COHERE_AVAILABLE and settings.COHERE_API_KEY:
            self.cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
            logger.info("Cliente Cohere inicializado")
        else:
            logger.warning("Cohere no disponible: falta SDK o COHERE_API_KEY")
    
        if LIGHTRAG_AVAILABLE:
            self._initialize_lightrag()
    
        logger.info(f"LegalRAG Engine inicializado en {working_dir} ({len(self.documents)} documentos cargados del disco)")

    # ── Persistencia de documentos en disco ──────────────────────────────
    
    @property
    def _documents_store_path(self) -> Path:
        return self.working_dir / self._DOCUMENTS_STORE_FILENAME
    
    def _load_documents_from_disk(self):
        """Carga self.documents desde el archivo JSON persistido"""
        store_path = self._documents_store_path
        if store_path.exists():
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
                logger.info(f"Cargados {len(self.documents)} documentos desde {store_path}")
            except Exception as e:
                logger.error(f"Error cargando documentos persistidos: {e}")
                self.documents = {}
        else:
            logger.info("No se encontró archivo de documentos persistidos, iniciando vacío")
    
    def _save_documents_to_disk(self):
        """Persiste self.documents a disco como JSON"""
        store_path = self._documents_store_path
        try:
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)
            logger.debug(f"Documentos persistidos: {len(self.documents)} docs en {store_path}")
        except Exception as e:
            logger.error(f"Error persistiendo documentos: {e}")
    
    async def load_processed_documents(self, processed_dir: str = "./docs/processed"):
        """
        Carga documentos .md ya procesados que no estén en self.documents.
        Útil para sincronizar el estado tras despliegues o migraciones.
        """
        processed_path = Path(processed_dir)
        if not processed_path.exists():
            logger.warning(f"Directorio de procesados no existe: {processed_path}")
            return 0
        
        md_files = list(processed_path.glob("**/*.md"))
        loaded = 0
        for md_file in md_files:
            doc_id = md_file.stem
            if doc_id in self.documents:
                continue  # Ya está cargado
            
            try:
                content = md_file.read_text(encoding="utf-8")
                if len(content.strip()) < 50:
                    continue  # Archivo vacío o casi vacío
                
                metadata = {
                    "filename": md_file.name,
                    "title": doc_id,
                    "document_type": "legal_document",
                    "source": "disk_reload",
                }
                
                self.documents[doc_id] = {
                    "content": content,
                    "metadata": metadata,
                    "chunks": self._chunk_content(content),
                }
                loaded += 1
            except Exception as e:
                logger.warning(f"Error cargando {md_file}: {e}")
        
        if loaded > 0:
            self._save_documents_to_disk()
            logger.info(f"Cargados {loaded} documentos nuevos desde {processed_path}")
        else:
            logger.info("No hay documentos nuevos por cargar desde disco")
        
        return loaded

    # ── LightRAG initialization ─────────────────────────────────────────
    
    def _initialize_lightrag(self):
        """Inicializa LightRAG con Cohere embeddings y LLM reales"""
        
        cohere_client = self.cohere_client
        
        async def cohere_embedding_func(texts: List[str]):
            """Genera embeddings reales con Cohere embed-multilingual-v3.0"""
            import numpy as np
            
            if cohere_client is None:
                raise RuntimeError("Cohere client no inicializado. Verifica COHERE_API_KEY.")
            
            all_embeddings = []
            batch_size = settings.EMBEDDING_BATCH_SIZE
            
            # Procesar en batches (Cohere limita a 96 textos por llamada)
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    response = await cohere_client.embed(
                        texts=batch,
                        model=settings.COHERE_EMBED_MODEL,
                        input_type="search_document",
                        embedding_types=["float"],
                    )
                    batch_embeddings = response.embeddings.float_
                    all_embeddings.extend(batch_embeddings)
                except Exception as e:
                    logger.error(f"Error generando embeddings (batch {i//batch_size}): {e}")
                    raise
            
            return np.array(all_embeddings, dtype=np.float32)
        
        async def cohere_llm_func(prompt: str, **kwargs) -> str:
            """Procesa con Cohere LLM para extracción de grafo de conocimiento"""
            if cohere_client is None:
                raise RuntimeError("Cohere client no inicializado. Verifica COHERE_API_KEY.")
            
            try:
                response = await cohere_client.chat(
                    message=prompt,
                    model=settings.COHERE_LLM_MODEL,
                    temperature=settings.COHERE_TEMPERATURE,
                    max_tokens=settings.COHERE_MAX_TOKENS,
                )
                return response.text
            except Exception as e:
                logger.error(f"Error en Cohere LLM: {e}")
                return ""
        
        # Inicializar LightRAG con funciones reales
        self.rag = LightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=cohere_llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=settings.EMBEDDING_DIM,
                max_token_size=8192,
                func=cohere_embedding_func
            )
        )
        
        logger.info(f"LightRAG inicializado con Cohere (embed={settings.COHERE_EMBED_MODEL}, llm={settings.COHERE_LLM_MODEL})")
    
    async def initialize_storages(self):
        """
        Inicializa los storages de LightRAG de forma asíncrona
        REQUERIDO por LightRAG para evitar StorageNotInitializedError
        """
        try:
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                if not self._storages_initialized:
                    await self.rag.initialize_storages()
                    self._storages_initialized = True
                    logger.info("LightRAG storages inicializados correctamente")
                else:
                    logger.debug("Storages ya inicializados, saltando...")
            else:
                logger.info("LightRAG no disponible, usando modo fallback")
                self._storages_initialized = True  # Marcar como inicializado en modo fallback
        except Exception as e:
            logger.error(f"Error inicializando storages: {e}")
            # Marcar como inicializado para evitar reintentos infinitos
            self._storages_initialized = True
    
    async def _ensure_storages_initialized(self):
        """Asegura que los storages estén inicializados antes de cualquier operación"""
        if not self._storages_initialized:
            logger.info("Storages no inicializados, inicializando ahora...")
            await self.initialize_storages()
    
    async def add_document(self, content: str, metadata: Dict[str, Any], document_id: str):
        """Agrega un documento al sistema RAG"""
        
        try:
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                # Asegurar que los storages estén inicializados ANTES de cualquier operación
                await self._ensure_storages_initialized()
                
                # Ahora sí, insertar el documento
                await self.rag.ainsert(content)
                logger.info(f"Documento {document_id} agregado a LightRAG")
            
            # SIEMPRE guardar en fallback local también (para búsqueda rápida)
            self.documents[document_id] = {
                "content": content,
                "metadata": metadata,
                "chunks": self._chunk_content(content)
            }
            
            if not LIGHTRAG_AVAILABLE or self.rag is None:
                logger.info(f"Documento {document_id} guardado localmente (modo fallback)")
            
            # Persistir a disco
            self._save_documents_to_disk()
                
        except Exception as e:
            logger.error(f"Error agregando documento {document_id}: {str(e)}")
            # Fallback a almacenamiento local en caso de error
            self.documents[document_id] = {
                "content": content,
                "metadata": metadata,
                "chunks": self._chunk_content(content)
            }
            self._save_documents_to_disk()
            logger.info(f"Documento {document_id} guardado en modo fallback debido a error")
    
    async def query(self, question: str, param: str = "naive") -> Dict[str, Any]:
        """
        Realiza una consulta al sistema RAG
        
        Args:
            question: Pregunta del usuario
            param: Tipo de consulta (naive, local, global, hybrid)
            
        Returns:
            Dict con respuesta y fuentes
        """
        
        try:
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                # Asegurar que los storages estén inicializados
                await self._ensure_storages_initialized()
                
                # Usar LightRAG real con modo válido
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
            # Intentar fallback
            try:
                return await self._fallback_query(question)
            except:
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
    
    async def query_with_rerank(
        self,
        query: str,
        top_k: Optional[int] = None,
        rerank_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Búsqueda avanzada con Cohere Rerank.
        
        1. Recupera candidatos amplios de LightRAG
        2. Reranquea con Cohere rerank-multilingual-v3.0
        3. Retorna top-K con scores de relevancia
        
        Args:
            query: Consulta del usuario
            top_k: Documentos finales (default: settings.RERANK_TOP_K)
            rerank_candidates: Candidatos iniciales (default: settings.RERANK_CANDIDATES)
        """
        top_k = top_k or settings.RERANK_TOP_K
        rerank_candidates = rerank_candidates or settings.RERANK_CANDIDATES
        
        try:
            # PASO 1: Obtener candidatos de LightRAG
            candidate_docs = []
            lightrag_answer = ""
            
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                await self._ensure_storages_initialized()
                
                try:
                    raw_result = await self.rag.aquery(
                        query,
                        param=QueryParam(mode="hybrid")
                    )
                    lightrag_answer = raw_result
                except Exception as e:
                    logger.warning(f"LightRAG query falló, usando fallback local: {e}")
            
            # Reunir documentos candidatos del almacén local
            for doc_id, doc_data in self.documents.items():
                for i, chunk in enumerate(doc_data["chunks"]):
                    candidate_docs.append({
                        "id": f"{doc_id}_chunk_{i}",
                        "document_id": doc_id,
                        "content": chunk,
                        "metadata": doc_data["metadata"],
                    })
            
            if not candidate_docs:
                return {
                    "answer": lightrag_answer or "No hay documentos disponibles para buscar.",
                    "documents": [],
                    "rerank_scores": [],
                    "sources": [],
                    "method": "no_documents",
                }
            
            # Limitar candidatos
            candidate_docs = candidate_docs[:rerank_candidates]
            
            # PASO 2: Reranquear con Cohere
            if self.cohere_client and COHERE_AVAILABLE:
                try:
                    rerank_response = await self.cohere_client.rerank(
                        query=query,
                        documents=[doc["content"] for doc in candidate_docs],
                        model=settings.COHERE_RERANK_MODEL,
                        top_n=top_k,
                    )
                    
                    reranked_docs = []
                    rerank_scores = []
                    
                    for result in rerank_response.results:
                        idx = result.index
                        doc = candidate_docs[idx]
                        doc["relevance_score"] = result.relevance_score
                        reranked_docs.append(doc)
                        rerank_scores.append(result.relevance_score)
                    
                    sources = list({
                        doc["metadata"].get("filename", doc["metadata"].get("title", "Desconocido"))
                        for doc in reranked_docs
                    })
                    
                    return {
                        "answer": lightrag_answer or self._build_context_from_docs(reranked_docs),
                        "documents": reranked_docs,
                        "rerank_scores": rerank_scores,
                        "sources": sources,
                        "method": "cohere_rerank",
                        "total_candidates": len(candidate_docs),
                    }
                    
                except Exception as e:
                    logger.error(f"Cohere rerank falló, usando fallback: {e}")
            
            # PASO 3: Fallback sin rerank (keyword scoring)
            return await self._fallback_rerank(query, candidate_docs, top_k, lightrag_answer)
            
        except Exception as e:
            logger.error(f"Error en query_with_rerank: {e}")
            return {
                "answer": "Error procesando la consulta.",
                "documents": [],
                "rerank_scores": [],
                "sources": [],
                "method": "error",
                "error": str(e),
            }
    
    async def _fallback_rerank(
        self, query: str, candidates: List[Dict], top_k: int, lightrag_answer: str
    ) -> Dict[str, Any]:
        """Fallback de reranking basado en keywords cuando Cohere no está disponible"""
        query_words = set(query.lower().split())
        
        for doc in candidates:
            content_words = set(doc["content"].lower().split())
            common = query_words & content_words
            doc["relevance_score"] = len(common) / max(len(query_words), 1)
        
        candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
        top_docs = candidates[:top_k]
        
        sources = list({
            doc["metadata"].get("filename", doc["metadata"].get("title", "Desconocido"))
            for doc in top_docs
        })
        
        return {
            "answer": lightrag_answer or self._build_context_from_docs(top_docs),
            "documents": top_docs,
            "rerank_scores": [doc["relevance_score"] for doc in top_docs],
            "sources": sources,
            "method": "fallback_keyword_rerank",
            "total_candidates": len(candidates),
        }
    
    def _build_context_from_docs(self, docs: List[Dict]) -> str:
        """Construye texto de contexto a partir de documentos rerankeados"""
        if not docs:
            return "No se encontraron documentos relevantes."
        
        context_parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.get("metadata", {}).get("title", "Fuente desconocida")
            score = doc.get("relevance_score", 0)
            context_parts.append(
                f"[Fuente {i}: {source} (relevancia: {score:.2f})]\n{doc['content'][:800]}"
            )
        
        return "\n\n---\n\n".join(context_parts)
    
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
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                await self._ensure_storages_initialized()
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
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                await self._ensure_storages_initialized()
                
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
        
        if LIGHTRAG_AVAILABLE and self.rag is not None:
            # Obtener documentos de LightRAG
            try:
                await self._ensure_storages_initialized()
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
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                await self._ensure_storages_initialized()
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
            "storages_initialized": self._storages_initialized,
            "working_directory": str(self.working_dir),
            "documents_by_type": {}
        }
        
        # Agrupar por tipo de documento
        for doc_id, doc_data in self.documents.items():
            doc_type = doc_data["metadata"].get("document_type", "unknown")
            stats["documents_by_type"][doc_type] = stats["documents_by_type"].get(doc_type, 0) + 1
        
        return stats