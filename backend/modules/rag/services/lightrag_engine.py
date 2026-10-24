import asyncio
import logging
from typing import Dict, List, Any, Optional
import json
import hashlib
import re
import math
import unicodedata
from collections import Counter
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

    logging.getLogger("lightrag").disabled = True
    LIGHTRAG_AVAILABLE = True
except Exception as e:
    logger.warning("operation_failed error_type={}", type(e).__name__)
    LIGHTRAG_AVAILABLE = False


def _select_graph_storage() -> str:
    """Cargar la compatibilidad con Neo4j solo si el backend opcional está habilitado."""
    if not settings.NEO4J_ENABLED:
        return "NetworkXStorage"

    try:
        from lightrag.kg.neo4j_impl import Neo4JStorage  # noqa: F401
    except ImportError:
        logger.warning("Neo4j storage unavailable; using NetworkX")
        return "NetworkXStorage"

    if not (settings.NEO4J_URI and settings.NEO4J_PASSWORD):
        logger.warning("NEO4J_ENABLED=true but credentials are missing; using NetworkX")
        return "NetworkXStorage"

    import os

    os.environ["NEO4J_URI"] = settings.NEO4J_URI
    os.environ["NEO4J_USERNAME"] = settings.NEO4J_USER
    os.environ["NEO4J_PASSWORD"] = settings.NEO4J_PASSWORD
    os.environ["NEO4J_DATABASE"] = settings.NEO4J_DATABASE
    logger.info("Neo4j enabled")
    return "Neo4JStorage"


# Puntuación mínima del reranker para conservar un documento (el harness mide su coste).
RERANK_MIN_SCORE = 0.1


class LegalRAGEngine:
    """Motor RAG especializado para documentos legales con LightRAG + Cohere"""

    _DOCUMENTS_STORE_FILENAME = "documents_store.json"

    def get_cache_revision(self) -> Optional[str]:
        """Snapshot identity; remote graphs have no shared revision contract yet."""
        if not settings.LOAD_LOCAL_KG or settings.NEO4J_ENABLED:
            return (
                None  # Disable answer caching instead of serving stale remote evidence.
            )
        snapshot = json.dumps(
            self.documents, sort_keys=True, ensure_ascii=False, default=str
        )
        return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()

    def __init__(self, working_dir: str = "./docs/knowledge_graph"):
        self.working_dir = Path(working_dir)

        # Solo crear directorio si LOAD_LOCAL_KG está habilitado
        if settings.LOAD_LOCAL_KG:
            self.working_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(
                "LOAD_LOCAL_KG=false, no se cargará grafo local (usando Neo4j Aura)"
            )

        self.documents = {}
        self.embeddings = {}
        self.rag = None
        self._storages_initialized = False
        self._initialized = False  # Flag para lazy initialization

        # Cargar documentos persistidos del disco solo si LOAD_LOCAL_KG está habilitado
        if settings.LOAD_LOCAL_KG:
            self._load_documents_from_disk()

        # Inicializar cliente Cohere - lazy initialization
        self.cohere_client = None
        self._cohere_initialized = False

        logger.info(
            f"LegalRAG Engine inicializado en {working_dir} ({len(self.documents)} documentos cargados del disco) - lazy initialization enabled"
        )

    def _ensure_initialized(self):
        """Lazy initialization de Cohere y LightRAG cuando se necesiten"""
        if self._initialized:
            return

        # Inicializar cliente Cohere
        if (
            not self._cohere_initialized
            and COHERE_AVAILABLE
            and settings.COHERE_API_KEY
        ):
            self.cohere_client = cohere.AsyncClient(api_key=settings.COHERE_API_KEY)
            logger.info("Cliente Cohere inicializado")
            self._cohere_initialized = True
        elif not self._cohere_initialized:
            logger.warning("Cohere no disponible: falta SDK o COHERE_API_KEY")

        # Inicializar LightRAG
        if LIGHTRAG_AVAILABLE and not self._initialized:
            self._initialize_lightrag()

        self._initialized = True

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
                logger.info(
                    f"Cargados {len(self.documents)} documentos desde {store_path}"
                )
            except Exception as e:
                logger.error("operation_failed error_type={}", type(e).__name__)
                self.documents = {}
        else:
            logger.info(
                "No se encontró archivo de documentos persistidos, iniciando vacío"
            )

    def _save_documents_to_disk(self):
        """Persiste self.documents a disco como JSON"""
        store_path = self._documents_store_path
        try:
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)
            logger.debug(
                f"Documentos persistidos: {len(self.documents)} docs en {store_path}"
            )
        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)

    async def load_processed_documents(self, processed_dir="./docs/processed"):
        return await asyncio.to_thread(self._load_processed_documents_sync, processed_dir)

    def _load_processed_documents_sync(self, processed_dir: str = "./docs/processed"):
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

            try:
                content = md_file.read_text(encoding="utf-8")
                if doc_id in self.documents and self.documents[doc_id].get("content") == content:
                    continue
                if not content.strip():
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
                logger.error("corpus_file_failed error_type={}", type(e).__name__)
                raise

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
                raise RuntimeError(
                    "Cohere client no inicializado. Verifica COHERE_API_KEY."
                )

            all_embeddings = []
            batch_size = settings.EMBEDDING_BATCH_SIZE

            # Procesar en batches (Cohere limita a 96 textos por llamada)
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
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
                    logger.error("operation_failed error_type={}", type(e).__name__)
                    raise

            return np.array(all_embeddings, dtype=np.float32)

        async def cohere_llm_func(prompt: str, **kwargs) -> str:
            """Procesa con Cohere LLM para extracción de grafo de conocimiento"""
            if cohere_client is None:
                raise RuntimeError(
                    "Cohere client no inicializado. Verifica COHERE_API_KEY."
                )

            try:
                response = await cohere_client.chat(
                    message=prompt,
                    model=settings.COHERE_LLM_MODEL,
                    temperature=settings.COHERE_TEMPERATURE,
                    max_tokens=settings.COHERE_MAX_TOKENS,
                )
                return response.text
            except Exception as error:
                logger.error(f"Error en Cohere LLM: {type(error).__name__}")
                return ""

        graph_storage = _select_graph_storage()

        # Inicializar LightRAG con funciones reales
        self.rag = LightRAG(
            working_dir=str(self.working_dir),
            llm_model_func=cohere_llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=settings.EMBEDDING_DIM,
                max_token_size=8192,
                func=cohere_embedding_func,
            ),
            graph_storage=graph_storage,
        )

        storage_type = (
            "Neo4j" if graph_storage == "Neo4JStorage" else "NetworkX (local)"
        )
        logger.info(
            f"LightRAG inicializado con Cohere (embed={settings.COHERE_EMBED_MODEL}, llm={settings.COHERE_LLM_MODEL}, graph_storage={storage_type})"
        )

    async def initialize_storages(self):
        """Truthful graph state; failures propagate for bounded startup retries."""
        self._ensure_initialized()
        if not LIGHTRAG_AVAILABLE or self.rag is None:
            self._storages_initialized = False
            return False  # Local lexical retrieval is explicitly separate from graph readiness.
        if self._storages_initialized:
            return True
        try:
            await self.rag.initialize_storages()
        except Exception as error:
            self._storages_initialized = False
            logger.error("rag_storage_failed error_type={}", type(error).__name__)
            raise
        self._storages_initialized = True
        return True


    async def _ensure_storages_initialized(self):
        """Asegura que los storages estén inicializados antes de cualquier operación"""
        if not self._storages_initialized:
            logger.info("Storages no inicializados, inicializando ahora...")
            await self.initialize_storages()

    async def add_document(
        self, content: str, metadata: Dict[str, Any], document_id: str
    ):
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
                "chunks": self._chunk_content(content),
            }

            if not LIGHTRAG_AVAILABLE or self.rag is None:
                logger.info(
                    f"Documento {document_id} guardado localmente (modo fallback)"
                )

            # Persistir a disco
            self._save_documents_to_disk()

        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)
            # Alternativa: almacenamiento local en caso de error
            self.documents[document_id] = {
                "content": content,
                "metadata": metadata,
                "chunks": self._chunk_content(content),
            }
            self._save_documents_to_disk()
            logger.info(
                f"Documento {document_id} guardado en modo fallback debido a error"
            )

    async def query(self, question: str, param: str = "naive") -> Dict[str, Any]:
        """
        Realiza una consulta al sistema RAG

        Argumentos:
            question: Pregunta del usuario
            param: Tipo de consulta (naive, local, global, hybrid)

        Retorna:
            Dict con respuesta y fuentes
        """

        try:
            if LIGHTRAG_AVAILABLE and self.rag is not None:
                # Asegurar que los storages estén inicializados
                await self._ensure_storages_initialized()

                # Usar LightRAG real con modo válido
                result = await self.rag.aquery(question, param=QueryParam(mode=param))

                return {
                    "answer": result,
                    "sources": self._extract_sources_from_result(result),
                    "confidence": self._calculate_confidence(result),
                    "method": "lightrag",
                }
            else:
                # Implementación fallback simple
                return await self._fallback_query(question)

        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)
            # Intentar fallback
            try:
                return await self._fallback_query(question)
            except:
                return {
                    "answer": "No se pudo procesar la consulta en este momento.",
                    "sources": [],
                    "confidence": 0.0,
                    "error": str(e),
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
                best_match["content"], question
            )

            return {
                "answer": f"Basado en los documentos disponibles: {relevant_text[:500]}...",
                "sources": [best_match["metadata"].get("filename", "Unknown")],
                "confidence": best_score,
                "method": "fallback_keyword",
            }
        else:
            return {
                "answer": "No se encontró información relevante en los documentos procesados.",
                "sources": [],
                "confidence": 0.0,
                "method": "fallback_no_match",
            }

    @staticmethod
    def _retrieval_tokens(text):
        normalized = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
        stop = {"de", "la", "el", "los", "las", "un", "una", "y", "o", "en", "del", "al", "que", "es", "por", "para", "con", "como", "mi", "su"}
        return [t for t in re.findall(r"[a-z0-9]+", normalized) if t not in stop]

    def _local_candidates(self, query, limit):
        """BM25 over ALL chunks before the candidate budget, with stable tie-breaking."""
        candidates = []
        for doc_id, data in self.documents.items():
            for i, chunk in enumerate(data.get("chunks", [])):
                if not isinstance(chunk, str) or not chunk.strip():
                    continue
                candidates.append({"id": f"{doc_id}_chunk_{i}", "document_id": doc_id,
                    "content": chunk, "metadata": data.get("metadata", {})})
        terms = set(self._retrieval_tokens(query))
        token_counts = [Counter(self._retrieval_tokens(d["content"])) for d in candidates]
        n = len(candidates)
        avg_len = sum(sum(c.values()) for c in token_counts) / max(n, 1)
        df = {term: sum(term in c for c in token_counts) for term in terms}
        ranked = []
        for doc, counts in zip(candidates, token_counts):
            length = sum(counts.values())
            score = sum(math.log(1+(n-df[t]+0.5)/(df[t]+0.5)) *
                (counts[t]*2.5)/(counts[t]+1.5*(0.25+0.75*length/max(avg_len,1)))
                for t in terms if counts[t])
            if score > 0:
                ranked.append((score, hashlib.sha256(doc["content"].encode()).hexdigest(), doc["id"], doc))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[3] for item in ranked[:limit]]

    def _retrieval_result(self, documents, method, count):
        sources = sorted({d["metadata"].get("filename", d["metadata"].get("title", "Desconocido")) for d in documents})
        return {"answer": self._build_context_from_docs(documents) if documents else "No hay evidencia suficiente en el corpus.",
                "documents": documents, "rerank_scores": [d["relevance_score"] for d in documents],
                "sources": sources, "method": method, "total_candidates": count}

    async def _graph_docs(self, query, mode, budget):
        """Chunks nativos de LightRAG para ``mode``; ``[]`` si no está disponible o falla."""
        docs = []
        if LIGHTRAG_AVAILABLE and self.rag is not None:
            try:
                await self._ensure_storages_initialized()
                raw = await self.rag.aquery_data(query, param=QueryParam(mode=mode, top_k=budget, chunk_top_k=budget))
                for chunk in raw.get("data", {}).get("chunks", []):
                    if not chunk.get("content"):
                        continue
                    identity = chunk.get("chunk_id") or hashlib.sha256(chunk["content"].encode()).hexdigest()
                    docs.append({"id": identity, "document_id": identity, "content": chunk["content"],
                        "metadata": {"filename": chunk.get("file_path", "Desconocido"),
                                     "reference_id": chunk.get("reference_id"), "retrieval_origin": "lightrag"}})
            except Exception as error:
                logger.warning("graph_retrieval_failed error_type={}", type(error).__name__)
        return docs

    async def query_with_rerank(self, query, top_k=None, rerank_candidates=None, trace=None):
        """Recupera y reordena. ``trace`` (dict) recibe los pasos intermedios para el harness de
        evaluación; no cambia el resultado. Con ``trace`` se piden al reranker las puntuaciones de
        *todos* los candidatos para medir cuánta evidencia relevante descarta el umbral."""
        self._ensure_initialized()
        top_k = top_k or settings.RERANK_TOP_K
        budget = rerank_candidates or settings.RERANK_CANDIDATES
        if top_k < 1 or budget < 1:
            raise ValueError("Retrieval limits must be positive")
        graph_docs = await self._graph_docs(query, "mix", budget)
        local_docs = self._local_candidates(query, budget)
        # Native graph retrieval is semantic; reserve a bounded share before lexical fill.
        graph_docs = graph_docs[:max(1, budget//2)]
        seen, candidates = set(), []
        for doc in graph_docs + local_docs:
            digest = hashlib.sha256(doc["content"].encode()).hexdigest()
            if digest not in seen:
                seen.add(digest)
                candidates.append(doc)
            if len(candidates) >= budget:
                break
        if trace is not None:
            trace.update(graph_docs=graph_docs, local_docs=local_docs, candidates=candidates,
                         threshold=RERANK_MIN_SCORE, rerank=None, reranker="none")
        if not candidates:
            return self._retrieval_result([], "no_documents" if not self.documents else "no_match", 0)
        if self.cohere_client and COHERE_AVAILABLE:
            try:
                top_n = len(candidates) if trace is not None else min(top_k, len(candidates))
                result = await self.cohere_client.rerank(query=query, documents=[d["content"] for d in candidates],
                    model=settings.COHERE_RERANK_MODEL, top_n=top_n)
                entries = list(result.results)
                if trace is not None:
                    trace.update(reranker="cohere", rerank=[(e.index, e.relevance_score) for e in entries])
                selected = []
                for entry in entries[:top_k]:
                    if 0 <= entry.index < len(candidates) and RERANK_MIN_SCORE <= entry.relevance_score <= 1:
                        doc = dict(candidates[entry.index])
                        doc["relevance_score"] = entry.relevance_score
                        selected.append(doc)
                return self._retrieval_result(selected, "cohere_rerank" if selected else "no_match", len(candidates))
            except Exception as error:
                logger.warning("rerank_failed error_type={}", type(error).__name__)
        if trace is not None:
            trace["reranker"] = "fallback_keyword"
        return await self._fallback_rerank(query, candidates, top_k, "")


    async def _fallback_rerank(self, query, candidates, top_k, lightrag_answer=""):
        terms = set(self._retrieval_tokens(query))
        selected = []
        for candidate in candidates:
            doc = dict(candidate)
            score = len(terms & set(self._retrieval_tokens(doc["content"]))) / max(len(terms),1)
            if score >= 0.1:
                doc["relevance_score"] = score
                selected.append(doc)
        selected.sort(key=lambda d: (-d["relevance_score"], hashlib.sha256(d["content"].encode()).hexdigest(), d["id"]))
        return self._retrieval_result(selected[:top_k], "fallback_keyword_rerank" if selected else "no_match", len(candidates))


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
        sentences = content.split(". ")

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
        sentences = content.split(". ")

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
            logger.error("operation_failed error_type={}", type(e).__name__)
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
                    nodes.extend(
                        [
                            {"id": edge.source, "label": edge.source},
                            {"id": edge.target, "label": edge.target},
                        ]
                    )
                    edges.append(
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "label": edge.label,
                        }
                    )

                return {
                    "nodes": nodes,
                    "edges": edges,
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                }
            else:
                # Implementación fallback
                return {
                    "nodes": [],
                    "edges": [],
                    "total_nodes": 0,
                    "total_edges": 0,
                    "message": "Modo fallback - sin grafo disponible",
                }

        except Exception as e:
            logger.error("operation_failed error_type={}", type(e).__name__)
            return {"nodes": [], "edges": [], "error": str(e)}

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
                        "added_date": doc.get("added_date", "unknown"),
                    }
                    for doc in docs
                ]
            except:
                pass

        # Alternativa: listar documentos locales
        documents = []
        for doc_id, doc_data in self.documents.items():
            documents.append(
                {
                    "id": doc_id,
                    "title": doc_data["metadata"].get("title", doc_id),
                    "metadata": doc_data["metadata"],
                    "content_length": len(doc_data["content"]),
                    "chunks_count": len(doc_data["chunks"]),
                }
            )

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
            logger.error("operation_failed error_type={}", type(e).__name__)
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
                        fragments.append(
                            chunk[:200] + "..." if len(chunk) > 200 else chunk
                        )

                results.append(
                    {
                        "document_id": doc_id,
                        "title": doc_data["metadata"].get("title", doc_id),
                        "fragments": fragments[:3],  # Limitar a 3 fragmentos
                        "relevance": content.count(keyword_lower),
                    }
                )

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
            "documents_by_type": {},
        }

        # Agrupar por tipo de documento
        for doc_id, doc_data in self.documents.items():
            doc_type = doc_data["metadata"].get("document_type", "unknown")
            stats["documents_by_type"][doc_type] = (
                stats["documents_by_type"].get(doc_type, 0) + 1
            )

        return stats
