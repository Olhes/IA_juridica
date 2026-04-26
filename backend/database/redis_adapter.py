"""
Redis Adapter para IA Jurídica
Cache y sesiones con Redis para alto rendimiento
"""

import redis.asyncio as redis
import json
import pickle
from typing import Any, Optional, List, Dict, Union
from datetime import datetime, timedelta
from config.settings import settings


class RedisAdapter:
    """Adaptador asíncrono para Redis con soporte de cache y sesiones"""
    
    def __init__(self):
        self.client = None
        self.config = {
            'url': settings.REDIS_URL,
            'encoding': 'utf-8',
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True
        }
    
    async def initialize(self):
        """Inicializar cliente Redis"""
        try:
            self.client = redis.from_url(**self.config)
            await self.client.ping()
            print("✅ Cliente Redis inicializado")
        except Exception as e:
            print(f"❌ Error inicializando Redis: {e}")
            raise
    
    async def close(self):
        """Cerrar cliente Redis"""
        if self.client:
            await self.client.close()
            print("✅ Cliente Redis cerrado")
    
    # === Operaciones de Cache ===
    
    async def set_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        """Guardar valor en cache"""
        try:
            ttl = ttl or settings.CACHE_TTL
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            result = await self.client.setex(key, ttl, value)
            return result
        except Exception as e:
            print(f"❌ Error en set_cache: {e}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """Obtener valor de cache"""
        try:
            value = await self.client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            print(f"❌ Error en get_cache: {e}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """Eliminar clave de cache"""
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            print(f"❌ Error en delete_cache: {e}")
            return False
    
    async def clear_cache_pattern(self, pattern: str) -> int:
        """Eliminar claves por patrón"""
        try:
            keys = await self.client.keys(pattern)
            if keys:
                return await self.client.delete(*keys)
            return 0
        except Exception as e:
            print(f"❌ Error en clear_cache_pattern: {e}")
            return 0
    
    # === Context Engineering Cache ===
    
    async def cache_cultural_context(self, context_id: str, context_data: Dict[str, Any],
                                   ttl: int = 3600) -> bool:
        """Cachear contexto cultural"""
        key = f"cultural_context:{context_id}"
        return await self.set_cache(key, context_data, ttl)
    
    async def get_cached_cultural_context(self, context_id: str) -> Optional[Dict[str, Any]]:
        """Obtener contexto cultural cacheado"""
        key = f"cultural_context:{context_id}"
        return await self.get_cache(key)
    
    async def cache_context_search(self, query_hash: str, results: List[Dict[str, Any]],
                                 ttl: int = 1800) -> bool:
        """Cachear resultados de búsqueda de contextos"""
        key = f"context_search:{query_hash}"
        return await self.set_cache(key, results, ttl)
    
    async def get_cached_context_search(self, query_hash: str) -> Optional[List[Dict[str, Any]]]:
        """Obtener búsqueda de contextos cacheada"""
        key = f"context_search:{query_hash}"
        return await self.get_cache(key)
    
    # === Cache de Embeddings ===
    
    async def cache_embedding(self, text_hash: str, embedding: List[float],
                            ttl: int = 86400) -> bool:
        """Cachear embedding de texto"""
        key = f"embedding:{text_hash}"
        # Serializar embedding como string para Redis
        embedding_str = json.dumps(embedding)
        return await self.set_cache(key, embedding_str, ttl)
    
    async def get_cached_embedding(self, text_hash: str) -> Optional[List[float]]:
        """Obtener embedding cacheado"""
        key = f"embedding:{text_hash}"
        embedding_str = await self.get_cache(key)
        if embedding_str:
            try:
                return json.loads(embedding_str)
            except json.JSONDecodeError:
                return None
        return None
    
    # === Cache de RAG ===
    
    async def cache_rag_results(self, query_hash: str, rag_results: Dict[str, Any],
                              ttl: int = 1800) -> bool:
        """Cachear resultados de RAG"""
        key = f"rag:{query_hash}"
        return await self.set_cache(key, rag_results, ttl)
    
    async def get_cached_rag_results(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Obtener resultados RAG cacheados"""
        key = f"rag:{query_hash}"
        return await self.get_cache(key)
    
    async def cache_document_chunks(self, doc_id: str, chunks: List[Dict[str, Any]],
                                   ttl: int = 3600) -> bool:
        """Cachear chunks de documento"""
        key = f"doc_chunks:{doc_id}"
        return await self.set_cache(key, chunks, ttl)
    
    async def get_cached_document_chunks(self, doc_id: str) -> Optional[List[Dict[str, Any]]]:
        """Obtener chunks de documento cacheados"""
        key = f"doc_chunks:{doc_id}"
        return await self.get_cache(key)
    
    # === Sesiones de Usuario ===
    
    async def create_user_session(self, session_id: str, session_data: Dict[str, Any],
                                 ttl_hours: int = 24) -> bool:
        """Crear sesión de usuario en Redis"""
        key = f"session:{session_id}"
        ttl = ttl_hours * 3600
        return await self.set_cache(key, session_data, ttl)
    
    async def get_user_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Obtener sesión de usuario"""
        key = f"session:{session_id}"
        return await self.get_cache(key)
    
    async def update_user_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Actualizar sesión de usuario"""
        key = f"session:{session_id}"
        session_data = await self.get_user_session(session_id)
        if session_data:
            session_data.update(updates)
            return await self.set_cache(key, session_data)
        return False
    
    async def delete_user_session(self, session_id: str) -> bool:
        """Eliminar sesión de usuario"""
        key = f"session:{session_id}"
        return await self.delete_cache(key)
    
    # === Rate Limiting ===
    
    async def check_rate_limit(self, identifier: str, limit: int = 100,
                              window_seconds: int = 900) -> Dict[str, Any]:
        """Verificar rate limiting"""
        key = f"rate_limit:{identifier}"
        current_time = datetime.utcnow().timestamp()
        
        try:
            # Obtener conteo actual
            pipe = self.client.pipeline()
            pipe.zremrangebyscore(key, 0, current_time - window_seconds)
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window_seconds)
            
            results = await pipe.execute()
            current_requests = results[1]
            
            return {
                'allowed': current_requests < limit,
                'current': current_requests,
                'limit': limit,
                'remaining': max(0, limit - current_requests - 1),
                'reset_time': current_time + window_seconds
            }
        except Exception as e:
            print(f"❌ Error en rate limiting: {e}")
            return {'allowed': True, 'error': str(e)}
    
    # === Colas y Tareas ===
    
    async def enqueue_task(self, queue_name: str, task_data: Dict[str, Any]) -> bool:
        """Agregar tarea a cola"""
        try:
            task_str = json.dumps(task_data)
            result = await self.client.lpush(queue_name, task_str)
            return result > 0
        except Exception as e:
            print(f"❌ Error en enqueue_task: {e}")
            return False
    
    async def dequeue_task(self, queue_name: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Obtener tarea de cola"""
        try:
            result = await self.client.brpop(queue_name, timeout)
            if result:
                _, task_str = result
                return json.loads(task_str)
            return None
        except Exception as e:
            print(f"❌ Error en dequeue_task: {e}")
            return None
    
    async def get_queue_length(self, queue_name: str) -> int:
        """Obtener longitud de cola"""
        try:
            return await self.client.llen(queue_name)
        except Exception as e:
            print(f"❌ Error en get_queue_length: {e}")
            return 0
    
    # === Contadores y Estadísticas ===
    
    async def increment_counter(self, key: str, amount: int = 1) -> int:
        """Incrementar contador"""
        try:
            return await self.client.incrby(key, amount)
        except Exception as e:
            print(f"❌ Error en increment_counter: {e}")
            return 0
    
    async def get_counter(self, key: str) -> int:
        """Obtener valor de contador"""
        try:
            value = await self.client.get(key)
            return int(value) if value else 0
        except Exception as e:
            print(f"❌ Error en get_counter: {e}")
            return 0
    
    async def set_counter(self, key: str, value: int, ttl: int = None) -> bool:
        """Establecer contador"""
        try:
            if ttl:
                return await self.client.setex(key, ttl, value)
            else:
                return await self.client.set(key, value)
        except Exception as e:
            print(f"❌ Error en set_counter: {e}")
            return False
    
    # === Health Check ===
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud de Redis"""
        try:
            start_time = datetime.utcnow()
            await self.client.ping()
            info = await self.client.info()
            
            return {
                'status': 'healthy',
                'database': 'redis',
                'version': info.get('redis_version', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory_human', 'unknown'),
                'response_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'database': 'redis',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    # === Utilidades ===
    
    async def get_all_keys_pattern(self, pattern: str, limit: int = 100) -> List[str]:
        """Obtener claves por patrón"""
        try:
            return await self.client.keys(pattern)[:limit]
        except Exception as e:
            print(f"❌ Error en get_all_keys_pattern: {e}")
            return []
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """Obtener estadísticas de memoria"""
        try:
            info = await self.client.info('memory')
            return {
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', '0B'),
                'used_memory_rss': info.get('used_memory_rss', 0),
                'used_memory_peak': info.get('used_memory_peak', 0),
                'used_memory_peak_human': info.get('used_memory_peak_human', '0B')
            }
        except Exception as e:
            print(f"❌ Error en get_memory_usage: {e}")
            return {}


# Instancia global del adaptador
redis_adapter = RedisAdapter()
